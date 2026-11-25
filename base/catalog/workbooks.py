"""The WORKBOOK: its customer's part and its translations."""

import hashlib
import html
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from live.markdown import render_markdown
from live.meta import all_live_app_configs

from base.catalog.errors import WorkbookError
from base.workbook_sections import FENCE, behind, closes, current_body

WORKBOOK, WORKBOOK_TRANSLATION = "WORKBOOK.md", "WORKBOOK.{}.md"  # {}: the language of the translation
WORKBOOK_EN = WORKBOOK_TRANSLATION.format("en")
#: The line that ends the customer's part of a WORKBOOK; compared exactly, outside code blocks.
MAINTAINERS_HEADING = "## Para quien lo mantiene"

_COMMENT_START, _COMMENT_END = "<!--", "-->"
_HEADING_ID_RE = re.compile(r'<h[1-6][^>]*\sid="([^"]*)"')
_ANCHOR_RE = re.compile(r'<a\s[^>]*href="#([^"]*)"')


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


def _uncommented_lines(text: str) -> Iterator[tuple[str, bool]]:  # noqa: C901
    """Each line of ``text`` without its HTML comments, and whether it is in a fenced code block.

    The ``<!-- origen: … -->`` and ``<!-- código: … -->`` of a WORKBOOK tie it to ``MIGRATION.md``
    and to its sources, never reaching ``shared.app_doc`` nor the assistant;
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
            match = FENCE.match(line)
            if fence is not None or match:
                if fence is None:
                    fence = match.group(1)
                elif closes(fence, line):
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


@dataclass(frozen=True)
class Translation:
    """A module's WORKBOOK and the state of its translation into one language."""

    label: str
    source: str  # the Spanish customer's part
    path: Path
    state: str  # "missing", "current" or "stale"
    body: str = ""  # the translation without its marks, when current
    behind: tuple[str, ...] = ()  # the sections to translate again, when stale


def translate_by_hand(state: Translation) -> str:
    """How to bring a stale translation up to date, for the errors that find it.

    By hand: ERPlora uses no ``ANTHROPIC_API_KEY``, so no error sends to
    ``translate_workbooks`` without ``--check``, which calls the Claude API.
    """
    sections = "; ".join(state.behind) or "no section is missing: a heading or its mark is out of place"
    return (
        f"translate by hand into {state.path.name} each section of {WORKBOOK} that changed, with its mark on the "
        f"line under its heading (the same headings, in the same order): {sections}"
    )


def workbook_translation(config, language: str = "en") -> Translation:
    """The Spanish part of ``config``'s WORKBOOK and whether its translation into ``language`` is generated from it.

    Raises ``WorkbookError`` (via ``user_part``) and ``FileNotFoundError`` without ``WORKBOOK.md``.
    """
    root = Path(config.path)
    source = user_part((root / WORKBOOK).read_text(encoding="utf-8"))
    path = root / WORKBOOK_TRANSLATION.format(language)
    if not path.is_file():
        return Translation(config.label, source, path, "missing")
    text = path.read_text(encoding="utf-8")
    body = current_body(source, text)
    if body is None:
        return Translation(config.label, source, path, "stale", behind=tuple(behind(source, text)))
    return Translation(config.label, source, path, "current", body)


def workbook_configs(configs: Iterable | None = None) -> list:
    """The apps whose WORKBOOK is translated: every module, and every platform app with a WORKBOOK
    (``base``, which documents the Hub without being a module of the store: never in ``catalog_modules``)."""
    return [
        config
        for config in (all_live_app_configs() if configs is None else configs)
        if config.kind == "app" or (Path(config.path) / WORKBOOK).is_file()
    ]


def stale_translations(configs: Iterable | None = None, language: str = "en") -> dict[str, str]:
    """By label, what to do with each existing translation into ``language`` that its WORKBOOK left behind (``workbook_configs``)."""
    stale = {}
    for config in workbook_configs(configs):
        if (Path(config.path) / WORKBOOK).is_file():
            try:
                state = workbook_translation(config, language)
            except WorkbookError as error:
                # A module's: build_registry reports the WORKBOOK itself. A platform app's (base) no registry reads.
                if config.kind != "app":
                    stale[config.label] = f"{WORKBOOK}: {error}"
                continue
            if state.state == "stale":
                stale[config.label] = translate_by_hand(state)
    return stale
