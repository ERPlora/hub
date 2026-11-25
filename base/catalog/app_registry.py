"""The registry: what ``register_apps`` writes, read from the code alone (no database, no network)."""

import gettext
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.utils import translation
from django.utils.translation import pgettext_lazy
from live.markdown import IMAGE_EXTENSIONS
from live.meta import module_configs

from base.catalog.errors import RegistryError, WorkbookError
from base.catalog.workbooks import WORKBOOK, WORKBOOK_EN, check_anchors, translate_by_hand, workbook_translation

#: The images of a module's documentation, linked relatively from its WORKBOOK.
IMAGES_DIR = PurePosixPath("docs/img")
#: What ``_image_files`` reports of a file under ``docs/img/`` that is not published.
SYMLINK, OTHER_FORMAT = "symlink", "other_format"
#: ``{"<icon>": "<svg>"}``, versioned and written by ``pnpm gen:app-icons``.
APP_ICONS = PurePosixPath("frontend/generated/app-icons.json")
SPANISH_CATALOG = PurePosixPath("locale/es/LC_MESSAGES/django.mo")
#: Column lengths of ``shared.app`` the texts must fit in (``live.shared_catalog``).
TEXT_LIMITS = {"verbose_name": 80, "summary": 120}


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

    def pgettext(self, context, message):
        return None


#: What ``pgettext_lazy`` returns: every call shares the class, which keeps ``(context, message)`` in ``_args``.
_CONTEXTED = type(pgettext_lazy("", ""))


def _context(text) -> str | None:
    """The context ``text`` is said with when it is a ``pgettext_lazy`` (``None`` for any other text)."""
    return text._args[0] if isinstance(text, _CONTEXTED) else None


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
    catalogue, required even when both read the same. A text said with ``pgettext_lazy`` is read
    with its context, as Django reads it: never from the plain entry (hub#661)."""
    catalog = _spanish_catalog(config)
    texts = {}
    for attribute, column in (
        ("verbose_name", "name"),
        ("summary", "summary"),
        ("description", "description"),
    ):
        text = getattr(config, attribute)
        context = _context(text)
        with translation.override("en"):
            english = str(text)
        if catalog is None or not english:
            spanish = None
        elif context is None:
            spanish = catalog.gettext(english)
        else:
            spanish = catalog.pgettext(context, english)
        if not spanish:
            said = f"{english!r}" if context is None else f"{english!r} (context {context!r})"
            problems.append(
                f"{config.label}: {attribute}: no Spanish msgstr for {said} in "
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
            f"{translate_by_hand(state)}"
        )
    elif state.state == "current":
        try:
            check_anchors(state.body)
        except WorkbookError as error:
            problems.append(f"{config.label}: {WORKBOOK_EN}: {error}")
        else:
            docs["en"] = state.body
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
