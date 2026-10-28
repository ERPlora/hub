"""The Hub's modules, registered as products in the SaaS's ``shared`` schema (round 16, PLAN §21; spec §4).

Each module (``kind = "app"``) is one row of ``shared.app`` and up to two of ``shared.app_doc``,
written by ``register_apps`` from what the code already says: the ``LiveAppConfig`` metadata in
English and its Spanish catalogue, the icon baked in ``frontend/generated/app-icons.json`` and the
customer's part of ``WORKBOOK.md`` (Spanish) and of ``WORKBOOK.en.md`` (its versioned translation).

- ``user_part`` cuts the customer's part of a WORKBOOK (§4.1), without its HTML comments
  (PLAN-MIGRATIONS §5).
- ``build_registry`` reads it all without a database or the network (§4.2): ``register_apps
  --check`` and the image's build run it; every problem is gathered, naming the app and the field.
- ``register_apps`` writes the registry in one transaction on the ``shared`` alias (§4.2).
- ``AppImagesFinder`` publishes ``apps/<id>/docs/img/`` as ``static/catalog/<id>/img/`` (§4.4).
- ``known_verticals`` and ``template_apps`` derive PLAN §15.2's ``HUB_TEMPLATE_APPS`` (§4.7).

This module is the only one that imports ``shared.models`` and names the ``shared`` alias: the
explicit exception to «only ``services.py`` and ``queries.py`` touch the ORM», as
``base/tenancy/migrator.py`` is for the DDL (``base/tests/test_shared_lint.py``). It is no
``@operation``: it runs for no hub and no user, with the ``hub_shared`` role, which may only
``SELECT``, ``INSERT`` and ``UPDATE`` those two tables.
"""

import gettext
import hashlib
import html
import json
import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from django.conf import settings
from django.contrib.staticfiles.finders import BaseFinder
from django.contrib.staticfiles.utils import matches_patterns
from django.core.files.storage import FileSystemStorage
from django.db import DatabaseError, connections, transaction
from django.db.models import Max
from django.utils import timezone, translation
from live.markdown import IMAGE_EXTENSIONS, render_markdown
from live.meta import all_live_app_configs, module_configs
from live.shared_catalog import DOC_LANGUAGES

from base.routers import SHARED_ALIAS
from shared.models import App, AppDoc

logger = logging.getLogger(__name__)

WORKBOOK = "WORKBOOK.md"
WORKBOOK_EN = "WORKBOOK.en.md"
#: The line that ends the customer's part of a WORKBOOK; compared exactly, outside code blocks.
MAINTAINERS_HEADING = "## Para quien lo mantiene"
#: The images of a module's documentation, linked relatively from its WORKBOOK (spec decision 10).
IMAGES_DIR = PurePosixPath("docs/img")
#: What ``_image_files`` reports of a file under ``docs/img/`` that is not published.
SYMLINK, OTHER_FORMAT = "symlink", "other_format"
#: Where the finder publishes them: ``/static/catalog/<id>/img/<file>``.
STATIC_PREFIX = "catalog"
#: ``{"<icon>": "<svg>"}``, versioned and written by ``pnpm gen:app-icons`` (§4.6).
APP_ICONS = PurePosixPath("frontend/generated/app-icons.json")
SPANISH_CATALOG = PurePosixPath("locale/es/LC_MESSAGES/django.mo")
#: Column lengths of ``shared.app`` the texts must fit in (``live.shared_catalog``).
TEXT_LIMITS = {"verbose_name": 80, "summary": 120}

_HEADER_FORMAT = "<!-- generated from WORKBOOK.md sha256:{} -->"
#: What prints that first line for an app, in its Hub's checkout (PLAN-MIGRATIONS §24-D).
_HEADER_COMMAND = (
    'uv run python manage.py shell --no-imports -c "from django.apps import apps; from base import catalog; '
    "print(catalog.en_header(catalog.source_hash(catalog.workbook_translation(apps.get_app_config('{}')).source)))\""
)
_HEADER_RE = re.compile(
    r"\A<!-- generated from WORKBOOK\.md sha256:([0-9a-f]{64}) -->[ \t]*\n+"
)
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_COMMENT_START, _COMMENT_END = "<!--", "-->"
_HEADING_ID_RE = re.compile(r'<h[1-6][^>]*\sid="([^"]*)"')
_ANCHOR_RE = re.compile(r'<a\s[^>]*href="#([^"]*)"')
#: What register_apps needs on each table of ``shared`` (``bootstrap_databases`` grants it to hub_shared).
_TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE")
#: Two workers of a deploy in progress never write at the same time (released with the transaction).
_REGISTER_LOCK = (
    "SELECT pg_advisory_xact_lock(hashtext('erplora.shared.register_apps'))"
)


class CatalogError(Exception):
    """The registry cannot be built or written; the message says what and how to fix it."""


class SharedSchemaNotReady(CatalogError):
    """The SaaS has not created the ``shared`` tables yet (its first ``migrate``): wait, not a contract gap.

    The worker waits for them (``base.worker``); a table that exists without a column the mirror
    writes is a ``CatalogError`` instead, fatal (spec §3.5).
    """

    def __init__(self, tables: list[str]):
        self.tables = tables
        super().__init__(
            f"the SaaS has not migrated the shared schema yet: no table {', '.join(tables)} "
            "(saas-next's migrate creates them)"
        )


class WorkbookError(CatalogError):
    """A WORKBOOK whose customer's part cannot be published."""


class RegistryError(CatalogError):
    """Every problem of every module, gathered: one line each, ``<app>: <field>: <what>``."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(problems)

    def __str__(self) -> str:
        lines = "".join(f"\n- {problem}" for problem in self.problems)
        return f"{len(self.problems)} problem(s) in the apps' registry:{lines}"


# ── The WORKBOOK: its customer's part and its English translation ──────────────────────────────


def user_part(text: str) -> str:
    """The customer's part of a WORKBOOK: from its first ``## `` to ``## Para quien lo mantiene``.

    Before it (the title, ``Prefijo``, ``Alcance MVP``, ``Estado de la app`` and the quote) speaks
    of the process; after it, of the code. Its HTML comments go too (``_uncommented_lines``);
    nothing else is transformed. Raises ``WorkbookError`` without that heading (never a whole
    WORKBOOK by mistake), with nothing above it, with a comment that never closes, or when a
    ``](#…)`` link points at no heading of the part.
    """
    part = None
    for line, code in _uncommented_lines(text):
        if code:
            if part is not None:
                part.append(line)
            continue
        if line.rstrip() == MAINTAINERS_HEADING:
            break
        if part is None and line.startswith("## "):
            part = []
        if part is not None:
            part.append(line)
    else:
        raise WorkbookError(
            f"no «{MAINTAINERS_HEADING}» heading: write it where the customer's part ends "
            "(everything above it is published)."
        )
    if part is None:
        raise WorkbookError(f"nothing for the customer above «{MAINTAINERS_HEADING}».")
    published = "\n".join(part).strip() + "\n"
    check_anchors(published)
    return published


def _uncommented_lines(text: str) -> Iterator[tuple[str, bool]]:
    """Each line of ``text`` without its HTML comments, and whether it is in a fenced code block.

    The ``<!-- origen: … -->`` and ``<!-- código: … -->`` of a WORKBOOK tie it to ``MIGRATION.md``
    and to its sources, never reaching ``shared.app_doc`` nor the assistant (PLAN-MIGRATIONS §5);
    in a code block they are text, and a heading or a fence in a comment is not one. A line that
    was only a comment goes, and so do the blank lines it would double. Lazy: what ``user_part``
    never reads (the maintainers' part) is never checked. Raises ``WorkbookError`` when a comment
    is still open at the end.
    """
    fence = None
    opened = None  # the number of the line where the comment being skipped began
    last_blank, collapse = True, False
    for number, line in enumerate(text.splitlines(), start=1):
        if opened is None:
            match = _FENCE_RE.match(line)
            if fence is not None or match:
                if fence is None:
                    fence = match.group(1)
                elif _closes(fence, line):
                    fence = None
                last_blank, collapse = not line.strip(), False
                yield line, True
                continue
        commented = opened is not None or _COMMENT_START in line
        if commented:
            line, opened = _uncomment(line, opened, number)
        if line.strip():
            last_blank, collapse = False, False
            yield line, False
        elif commented:
            collapse = last_blank
        elif not collapse:
            last_blank = True
            yield line, False
    if opened is not None:
        raise WorkbookError(
            f"the HTML comment opened on line {opened} never closes: end it with «{_COMMENT_END}»."
        )


def _closes(fence: str, line: str) -> bool:
    """Whether ``line`` closes the fenced code block ``fence`` (its opening run of backticks or tildes) opened."""
    match = _FENCE_RE.match(line)
    return (
        match is not None
        and match.group(1)[0] == fence[0]
        and len(match.group(1)) >= len(fence)
        and not line.strip().lstrip(fence[0])
    )


def prose_lines(text: str) -> Iterator[tuple[int, str]]:
    """Each line of ``text`` outside its fenced code blocks, with its number (the first is 1)."""
    fence = None
    for number, line in enumerate(text.splitlines(), start=1):
        if fence is None:
            match = _FENCE_RE.match(line)
            if match:
                fence = match.group(1)
            else:
                yield number, line
        elif _closes(fence, line):
            fence = None


def _uncomment(line: str, opened: int | None, number: int) -> tuple[str, int | None]:
    """``line`` (number ``number``) without its comments, and where the one still open began.

    ``opened`` is that of the line before: the line starts inside a comment. The text on both
    sides of a comment is joined as it reads, with the space that was there and no other.
    """
    kept, rest = "", line
    while True:
        if opened is None:
            start = rest.find(_COMMENT_START)
            if start == -1:
                return kept + rest, None
            kept, rest = kept + rest[:start], rest[start + len(_COMMENT_START) :]
            opened = number
        end = rest.find(_COMMENT_END)
        if end == -1:
            return kept.rstrip(), opened
        rest, opened = rest[end + len(_COMMENT_END) :], None
        if not kept.strip():
            rest = rest.lstrip()
        elif not rest[:1].strip():
            kept = kept.rstrip()


def check_anchors(markdown: str) -> None:
    """Raises ``WorkbookError`` when a ``#…`` link points at no heading of ``markdown``.

    The ids are the ones ``live.markdown.render_markdown`` gives the headings (``slugify_unicode``),
    so a link that passes here works in the store.
    """
    rendered = render_markdown(markdown)
    ids = {html.unescape(heading_id) for heading_id in _HEADING_ID_RE.findall(rendered)}
    dangling = sorted(
        {
            f"#{target}"
            for anchor in _ANCHOR_RE.findall(rendered)
            if (target := unquote(html.unescape(anchor))) not in ids
        }
    )
    if dangling:
        raise WorkbookError(
            f"links to no heading of the published part: {', '.join(dangling)}."
        )


def source_hash(markdown: str) -> str:
    """sha256 in hex of a document: the ``source_hash`` of ``shared.app_doc``."""
    return hashlib.sha256(markdown.encode()).hexdigest()


def en_header(digest: str) -> str:
    """The first line of a ``WORKBOOK.en.md``: the hash of the Spanish part it was generated from."""
    return _HEADER_FORMAT.format(digest)


def translate_by_hand(label: str) -> str:
    """How to bring app ``label``'s stale ``WORKBOOK.en.md`` up to date, for the errors that find it.

    By hand: ERPlora uses no ``ANTHROPIC_API_KEY`` (PLAN-MIGRATIONS §24-D), so no error sends to
    ``translate_workbooks`` without ``--check``, which calls the Claude API. The header the command
    prints (``en_header`` of the current Spanish part) is what makes the translation current.
    """
    return (
        f"translate by hand the part of {WORKBOOK} that changed into {WORKBOOK_EN} and make its first "
        f"line the header this prints: {_HEADER_COMMAND.format(label)}"
    )


@dataclass(frozen=True)
class Translation:
    """A module's WORKBOOK and the state of its English translation."""

    label: str
    source: str  # the Spanish customer's part
    en_path: Path
    state: str  # "missing", "current" or "stale"
    en_body: str = ""  # WORKBOOK.en.md without its header, when current


def workbook_translation(config) -> Translation:
    """The Spanish part of ``config``'s WORKBOOK and whether ``WORKBOOK.en.md`` is generated from it.

    Raises ``WorkbookError`` (via ``user_part``) and ``FileNotFoundError`` without ``WORKBOOK.md``.
    """
    root = Path(config.path)
    source = user_part((root / WORKBOOK).read_text(encoding="utf-8"))
    en_path = root / WORKBOOK_EN
    if not en_path.is_file():
        return Translation(config.label, source, en_path, "missing")
    en_text = en_path.read_text(encoding="utf-8")
    match = _HEADER_RE.match(en_text)
    if match is None or match.group(1) != source_hash(source):
        return Translation(config.label, source, en_path, "stale")
    return Translation(config.label, source, en_path, "current", en_text[match.end() :])


def workbook_configs(configs: Iterable | None = None) -> list:
    """The apps whose ``WORKBOOK.en.md`` is generated: every module, and every platform app with a WORKBOOK
    (``base``, which documents the Hub without being a module of the store: never in ``catalog_modules``)."""
    return [
        config
        for config in (all_live_app_configs() if configs is None else configs)
        if config.kind == "app" or (Path(config.path) / WORKBOOK).is_file()
    ]


def stale_translations(configs: Iterable | None = None) -> list[str]:
    """Labels of the apps (``workbook_configs``) whose ``WORKBOOK.en.md`` exists and no longer matches their WORKBOOK."""
    stale = []
    for config in workbook_configs(configs):
        if (Path(config.path) / WORKBOOK).is_file():
            try:
                if workbook_translation(config).state == "stale":
                    stale.append(config.label)
            except WorkbookError:
                # A module's: build_registry reports the WORKBOOK itself. A platform app's (base) no
                # registry reads, so it counts here, and the header command of ``translate_by_hand``
                # (or ``translate_workbooks --app``, before any call) names the error.
                if config.kind != "app":
                    stale.append(config.label)
    return stale


# ── The registry (§4.2) ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AppEntry:
    """One row of ``shared.app`` (without the release's columns) and its documents by language."""

    id: str
    name_en: str
    name_es: str
    summary_en: str
    summary_es: str
    description_en: str
    description_es: str
    icon: str
    icon_svg: str
    category: str
    premium: bool
    requires: list[str]
    verticals: list[str]
    listed: bool
    docs: dict[str, str] = field(default_factory=dict)


def load_app_icons() -> dict[str, str] | None:
    """The baked icons (``frontend/generated/app-icons.json``), or ``None`` when it was never generated."""
    path = Path(settings.BASE_DIR) / APP_ICONS
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class _MissingTranslation(gettext.NullTranslations):
    """The fallback of an app's own catalogue: ``None`` tells «no msgstr» from «the same text»."""

    def gettext(self, message):
        return None


def _spanish_catalog(config) -> gettext.NullTranslations | None:
    path = Path(config.path) / SPANISH_CATALOG
    if not path.is_file():
        return None
    with path.open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)
    catalog.add_fallback(_MissingTranslation())
    return catalog


def _texts(config, problems: list[str]) -> dict[str, str]:
    """``name_en``, ``name_es``, ``summary_*`` and ``description_*``: English is the source (the
    ``gettext_lazy`` of the ``LiveAppConfig``), Spanish its msgstr in the app's own compiled
    catalogue, required even when both read the same."""
    catalog = _spanish_catalog(config)
    texts = {}
    for attribute, column in (
        ("verbose_name", "name"),
        ("summary", "summary"),
        ("description", "description"),
    ):
        with translation.override("en"):
            english = str(getattr(config, attribute))
        spanish = catalog.gettext(english) if catalog is not None and english else None
        if not spanish:
            problems.append(
                f"{config.label}: {attribute}: no Spanish msgstr for {english!r} in "
                f"apps/{config.label}/{SPANISH_CATALOG}: add it to django.po and run compilemessages."
            )
            continue
        limit = TEXT_LIMITS.get(attribute)
        too_long = [
            language
            for language, text in (("English", english), ("Spanish", spanish))
            if limit is not None and len(text) > limit
        ]
        if too_long:
            problems.append(
                f"{config.label}: {attribute}: the {' and '.join(too_long)} text is longer than "
                f"{limit} characters."
            )
            continue
        texts[f"{column}_en"], texts[f"{column}_es"] = english, spanish
    return texts


def _documents(config, problems: list[str]) -> dict[str, str]:
    """``{"es": <user part>, "en": <translation>}``: ``en`` only when it exists and is current."""
    if not (Path(config.path) / WORKBOOK).is_file():
        problems.append(
            f"{config.label}: {WORKBOOK}: missing; every module documents itself there."
        )
        return {}
    try:
        state = workbook_translation(config)
    except WorkbookError as error:
        problems.append(f"{config.label}: {WORKBOOK}: {error}")
        return {}
    docs = {"es": state.source}
    if state.state == "stale":
        problems.append(
            f"{config.label}: {WORKBOOK_EN}: out of date with {WORKBOOK}: "
            f"{translate_by_hand(config.label)}"
        )
    elif state.state == "current":
        try:
            check_anchors(state.en_body)
        except WorkbookError as error:
            problems.append(f"{config.label}: {WORKBOOK_EN}: {error}")
        else:
            docs["en"] = state.en_body
    return docs


def _image_files(app: Path) -> Iterator[tuple[PurePosixPath, str | None]]:
    """``(path relative to the app, problem)`` of everything under its ``docs/img/``, hidden ones left out.

    ``problem`` is ``None`` for an image to publish, ``OTHER_FORMAT`` for another extension and
    ``SYMLINK`` for a symbolic link, never followed: ``docs/img/x.png -> ../../../config/settings.py``
    would publish the settings. A linked ``docs`` or ``docs/img`` is the only entry.
    """
    for directory in (IMAGES_DIR.parent, IMAGES_DIR):
        if (app / directory).is_symlink():
            yield directory, SYMLINK
            return
    root = app / IMAGES_DIR
    if not root.is_dir():
        return
    # rglob does not descend into a linked folder: the link itself is reported.
    for path in sorted(root.rglob("*")):
        relative = PurePosixPath(path.relative_to(app).as_posix())
        if any(part.startswith(".") for part in relative.relative_to(IMAGES_DIR).parts):
            continue
        if path.is_symlink():
            yield relative, SYMLINK
        elif path.is_file():
            yield (
                relative,
                None if relative.suffix.lower() in IMAGE_EXTENSIONS else OTHER_FORMAT,
            )


def _through_symlink(app: Path, path: PurePosixPath) -> bool:
    """Whether ``app / path`` or any folder between ``app`` and it is a symbolic link."""
    return any(
        (app / PurePosixPath(*path.parts[:end])).is_symlink()
        for end in range(1, len(path.parts) + 1)
    )


def build_registry(
    configs: Iterable | None = None, *, icons: dict[str, str] | None = None
) -> list[AppEntry]:
    """What ``register_apps`` writes, read from the code alone: no database, no network.

    ``configs`` defaults to the installed modules (only ``kind = "app"``: platform apps are no
    products) and ``icons`` to ``frontend/generated/app-icons.json``. Sorted by label, with
    ``requires`` and ``verticals`` sorted. Raises ``RegistryError`` with every problem found.
    """
    icons = load_app_icons() if icons is None else icons
    problems: list[str] = []
    entries = []
    for config in sorted(catalog_modules(configs), key=lambda config: config.label):
        found: list[str] = []
        texts = _texts(config, found)
        icon_svg = (icons or {}).get(config.icon, "")
        if not icon_svg:
            found.append(
                f"{config.label}: icon: {config.icon!r} is not baked in {APP_ICONS}: run `pnpm gen:app-icons` "
                "and commit the result."
            )
        docs = _documents(config, found)
        files = list(_image_files(Path(config.path)))
        links = [str(path) for path, problem in files if problem == SYMLINK]
        if links:
            found.append(
                f"{config.label}: {IMAGES_DIR}: a symbolic link is never published (it could publish any "
                f"file of the image): replace {', '.join(links)} with the file or folder itself."
            )
        rejected = [
            str(path.relative_to(IMAGES_DIR))
            for path, problem in files
            if problem == OTHER_FORMAT
        ]
        if rejected:
            found.append(
                f"{config.label}: {IMAGES_DIR}: only {', '.join(sorted(IMAGE_EXTENSIONS))} are published; "
                f"remove or convert {', '.join(rejected)}."
            )
        problems += found
        if not found:
            entries.append(
                AppEntry(
                    id=config.label,
                    **texts,
                    icon=config.icon,
                    icon_svg=icon_svg,
                    category=str(
                        config.category.value
                        if hasattr(config.category, "value")
                        else config.category
                    ),
                    premium=bool(config.premium),
                    requires=sorted(config.requires),
                    verticals=sorted(config.verticals),
                    listed=bool(config.listed),
                    docs=docs,
                )
            )
    if problems:
        raise RegistryError(problems)
    return entries


def catalog_modules(configs: Iterable | None = None) -> list:
    """The modules among ``configs`` (default: the installed apps), platform apps left out."""
    return [
        config
        for config in (module_configs() if configs is None else configs)
        if config.kind == "app"
    ]


# ── Static files: the documentation's images (§4.4) ────────────────────────────────────────────


class AppImagesFinder(BaseFinder):
    """Publishes each module's ``docs/img/**`` as ``catalog/<id>/img/**``, nothing else.

    Only the extensions of spec decision 10 (``svg`` can carry script and would be served from the
    Hub admin's origin); never a ``WORKBOOK*.md``, code, a hidden file, a symbolic link (nor
    anything through one) or anything outside ``docs/img/``. ``collectstatic`` copies them to
    ``STATIC_ROOT`` (no hash: the path is stable) and ``runserver`` serves them at once.
    """

    def __init__(self, configs: Iterable | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.storages: dict[str, FileSystemStorage] = {}
        #: ``{label: the module's folder}``, for the storages above.
        self.apps: dict[str, Path] = {}
        for config in catalog_modules(configs):
            app = Path(config.path)
            if (app / IMAGES_DIR).is_dir():
                storage = FileSystemStorage(location=app / IMAGES_DIR)
                storage.prefix = f"{STATIC_PREFIX}/{config.label}/img"
                self.storages[config.label] = storage
                self.apps[config.label] = app

    def list(self, ignore_patterns):
        for label, storage in self.storages.items():
            for path, problem in _image_files(self.apps[label]):
                if problem is not None:
                    continue
                relative = str(path.relative_to(IMAGES_DIR))
                if not (
                    ignore_patterns and matches_patterns(relative, ignore_patterns)
                ):
                    yield relative, storage

    def find(self, path, find_all=False, **kwargs):
        found = []
        for label, storage in self.storages.items():
            relative = path.removeprefix(f"{storage.prefix}/")
            if relative == path:
                continue
            parts = PurePosixPath(relative).parts
            if not parts or any(
                part in ("", "..") or part.startswith(".") for part in parts
            ):
                continue
            app, published = self.apps[label], IMAGES_DIR.joinpath(*parts)
            candidate = app / published
            if (
                candidate.suffix.lower() in IMAGE_EXTENSIONS
                and candidate.is_file()
                and not _through_symlink(app, published)
            ):
                if not find_all:
                    return str(candidate)
                found.append(str(candidate))
        return found


# ── Verticals (§4.7) ───────────────────────────────────────────────────────────────────────────


def known_verticals(configs: Iterable | None = None) -> list[str]:
    """Every vertical some module belongs to, sorted: the ones ``/internal`` accepts (PLAN §15.2)."""
    return sorted(
        {
            vertical
            for config in catalog_modules(configs)
            for vertical in config.verticals
        }
    )


def template_apps(vertical: str, configs: Iterable | None = None) -> list[str]:
    """PLAN §15.2's ``HUB_TEMPLATE_APPS[vertical]``: the modules of that vertical, closed by ``requires``.

    A module lists a vertical only when every hub of it turns the module on at sign-up (in doubt,
    out); raises ``ValueError`` for a vertical no module lists.
    """
    modules = {config.label: config for config in catalog_modules(configs)}
    pending = [
        label for label, config in modules.items() if vertical in config.verticals
    ]
    if not pending:
        raise ValueError(f"Unknown vertical {vertical!r}: no module lists it.")
    closed: set[str] = set()
    while pending:
        label = pending.pop()
        if label not in closed:
            closed.add(label)
            pending.extend(modules[label].requires)
    return sorted(closed)


# ── The write: register_apps (§4.2) ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Release:
    """The release that writes: the image's commit (``APP_VERSION``) and its time (``APP_RELEASED_AT``)."""

    version: str
    released_at: datetime


@dataclass(frozen=True)
class RegisterResult:
    written: int  # apps of the code, upserted
    retired: int  # apps no longer in the code, unlisted by this run
    docs_changed: int  # documents inserted or changed
    skipped: bool  # a newer release had already registered its apps: nothing written
    apps: tuple[str, ...] = ()  # the labels written


def release() -> Release:
    """This image's release. Production demands both settings; locally: ``dev``, written now.

    A release is ordered by its commit's time, not its sha (shas do not sort) nor the time of the
    write (an old release that started late would look newer).
    """
    version, released_at = settings.APP_VERSION, settings.APP_RELEASED_AT
    if not settings.DEBUG:
        missing = [
            name
            for name, value in (
                ("APP_VERSION", version),
                ("APP_RELEASED_AT", released_at),
            )
            if not value
        ]
        if missing:
            raise CatalogError(
                f"{' and '.join(missing)} not set: the image's build fixes them (--build-arg) and "
                "register_apps never guesses a release in production."
            )
    try:
        moment = datetime.fromisoformat(released_at) if released_at else timezone.now()
    except ValueError as error:
        raise CatalogError(
            f"APP_RELEASED_AT={released_at!r} is not ISO 8601: {error}."
        ) from error
    if timezone.is_naive(moment):
        raise CatalogError(
            f"APP_RELEASED_AT={released_at!r} has no UTC offset: use the commit's time in ISO 8601."
        )
    return Release(version or "dev", moment)


def register_apps(
    registry: list[AppEntry] | None = None, *, force: bool = False
) -> RegisterResult:
    """Write the registry (default: ``build_registry()``) into ``shared``, in one transaction.

    Never overwrites what a newer release registered unless ``force`` (the deliberate rollback of
    spec §4.3), never deletes (a retired app is unlisted, a retired translation left empty) and
    leaves nothing written when anything fails: the error is logged and raised. Tables the SaaS has
    not created yet raise ``SharedSchemaNotReady`` without logging: the worker waits for them.
    """
    try:
        if SHARED_ALIAS not in settings.DATABASES:
            raise CatalogError(
                f"The {SHARED_ALIAS!r} database alias is not configured: register_apps needs "
                "SHARED_DB_USER and SHARED_DB_PASSWORD, which only the worker task has."
            )
        this = release()
        registry = build_registry() if registry is None else registry
        with transaction.atomic(using=SHARED_ALIAS):
            with connections[SHARED_ALIAS].cursor() as cursor:
                cursor.execute(_REGISTER_LOCK)
                _check_tables(cursor)
                _check_columns(cursor)
            newest = App.objects.using(SHARED_ALIAS).aggregate(
                newest=Max("registered_at")
            )["newest"]
            if newest is not None and newest > this.released_at and not force:
                logger.info(
                    "register_apps: a newer release (registered at %s) already registered its apps; "
                    "nothing written by %s (%s).",
                    newest.isoformat(),
                    this.version,
                    this.released_at.isoformat(),
                )
                return RegisterResult(
                    written=0, retired=0, docs_changed=0, skipped=True
                )
            _upsert_apps(registry, this)
            retired = _retire_missing(registry, this)
            docs_changed = _write_documents(registry)
    except SharedSchemaNotReady:
        # Not an error yet: the caller says how loud it is (the worker waits; the command fails).
        raise
    except (CatalogError, DatabaseError) as error:
        logger.error("register_apps: nothing written: %s", error)
        raise
    logger.info(
        "register_apps: %d apps written, %d retired, %d documents changed (release %s at %s).",
        len(registry),
        retired,
        docs_changed,
        this.version,
        this.released_at.isoformat(),
    )
    return RegisterResult(
        written=len(registry),
        retired=retired,
        docs_changed=docs_changed,
        skipped=False,
        apps=tuple(entry.id for entry in registry),
    )


def _schema_and_table(db_table: str) -> tuple[str, str]:
    """``("shared", "app")`` from the quoted ``'"shared"."app"'``."""
    schema, table = (part.strip('"') for part in db_table.split("."))
    return schema, table


def _check_tables(cursor) -> None:
    """Both tables of the mirror exist and this role may use them (spec §3.3 and §4.3).

    Missing, the SaaS has not migrated ``shared`` yet: ``SharedSchemaNotReady``, which the worker
    waits for. Present without the grants of ``bootstrap_databases``: a fatal ``CatalogError``
    naming them. Read from ``pg_catalog``, which every role sees whatever its grants:
    ``information_schema`` hides a table the role has no privilege on, which would pass for «not
    migrated yet» (the worker waiting for ever) or for «no column».
    """
    tables = [_schema_and_table(model._meta.db_table) for model in (App, AppDoc)]
    cursor.execute(
        "SELECT n.nspname, c.relname, has_schema_privilege(n.oid, 'USAGE'), "
        + ", ".join(
            f"has_table_privilege(c.oid, '{privilege}')"
            for privilege in _TABLE_PRIVILEGES
        )
        + ", current_user FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.relkind IN ('r', 'p') AND n.nspname = ANY(%s) AND c.relname = ANY(%s)",
        [
            sorted({schema for schema, _ in tables}),
            sorted({table for _, table in tables}),
        ],
    )
    present = {(row[0], row[1]): row for row in cursor.fetchall()}
    missing = [
        f"{schema}.{table}" for schema, table in tables if (schema, table) not in present
    ]
    if missing:
        raise SharedSchemaNotReady(missing)
    lacking, role = [], ""
    for schema, table in tables:
        _, _, usage, *granted, role = present[schema, table]
        if not usage and f"USAGE on schema {schema}" not in lacking:
            lacking.append(f"USAGE on schema {schema}")
        absent = [
            privilege
            for privilege, has in zip(_TABLE_PRIVILEGES, granted, strict=True)
            if not has
        ]
        if absent:
            lacking.append(f"{', '.join(absent)} on {schema}.{table}")
    if lacking:
        raise CatalogError(
            f"role {role} lacks {'; '.join(lacking)}: run bootstrap_databases (it grants hub_shared "
            "USAGE on the schema and SELECT, INSERT and UPDATE on its tables, also those the SaaS's "
            "migration creates later)."
        )


def _check_columns(cursor) -> None:
    """Every column of the mirror exists in the database (spec §3.5); one more there is no error."""
    tables = {model: _schema_and_table(model._meta.db_table) for model in (App, AppDoc)}
    cursor.execute(
        "SELECT table_schema, table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = ANY(%s) AND table_name = ANY(%s)",
        [
            sorted({schema for schema, _ in tables.values()}),
            sorted({table for _, table in tables.values()}),
        ],
    )
    present = {tuple(row) for row in cursor.fetchall()}
    missing = [
        f"{schema}.{table}.{column.column}"
        for model, (schema, table) in tables.items()
        for column in model._meta.concrete_fields
        if (schema, table, column.column) not in present
    ]
    if missing:
        raise CatalogError(
            f"the database has no column {', '.join(missing)}: migrate the SaaS first (its release that "
            "adds them goes before the Hub's that writes them)."
        )


def _upsert_apps(registry: list[AppEntry], this: Release) -> None:
    columns = [
        field.name for field in App._meta.concrete_fields if not field.primary_key
    ]
    App.objects.using(SHARED_ALIAS).bulk_create(
        [
            App(
                id=entry.id,
                name_en=entry.name_en,
                name_es=entry.name_es,
                summary_en=entry.summary_en,
                summary_es=entry.summary_es,
                description_en=entry.description_en,
                description_es=entry.description_es,
                icon=entry.icon,
                icon_svg=entry.icon_svg,
                category=entry.category,
                premium=entry.premium,
                requires=entry.requires,
                verticals=entry.verticals,
                listed=entry.listed,
                hub_version=this.version,
                registered_at=this.released_at,
            )
            for entry in registry
        ],
        update_conflicts=True,
        unique_fields=["id"],
        update_fields=columns,
    )


def _retire_missing(registry: list[AppEntry], this: Release) -> int:
    """Unlist the apps no longer in the code (never deleted); returns how many were listed."""
    gone = App.objects.using(SHARED_ALIAS).exclude(
        id__in=[entry.id for entry in registry]
    )
    retired = gone.filter(listed=True).count()
    gone.update(listed=False, hub_version=this.version, registered_at=this.released_at)
    return retired


def _write_documents(registry: list[AppEntry]) -> int:
    """Insert the new documents and change those whose hash changed; returns how many.

    A language that no longer exists (a deleted ``WORKBOOK.en.md``) is left with ``markdown = ""``,
    which the SaaS treats as absent: never a ``DELETE``.
    """
    docs = AppDoc.objects.using(SHARED_ALIAS)
    existing = {
        (doc.app_id, doc.lang): doc
        for doc in docs.filter(app_id__in=[entry.id for entry in registry])
    }
    now = timezone.now()
    created, changed = [], []
    for entry in registry:
        for lang in DOC_LANGUAGES:
            markdown = entry.docs.get(lang, "")
            digest = source_hash(markdown)
            doc = existing.get((entry.id, lang))
            if doc is None:
                if markdown:
                    created.append(
                        AppDoc(
                            app_id=entry.id,
                            lang=lang,
                            markdown=markdown,
                            source_hash=digest,
                            updated_at=now,
                        )
                    )
            elif doc.source_hash != digest:
                doc.markdown, doc.source_hash, doc.updated_at = markdown, digest, now
                changed.append(doc)
    docs.bulk_create(created)
    docs.bulk_update(changed, ["markdown", "source_hash", "updated_at"])
    return len(created) + len(changed)
