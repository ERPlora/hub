"""A module's help window, read from the customer's part of its WORKBOOK in one language.

The window only paints markdown. What it paints is cut here: what the module is for (the first section), the section of
each tab (each ``###`` under the screens heading, named as its tab; a ``####`` is a window inside it) and the flows that
are done on one of those tabs, of which only the title, the steps and what happens if they fail are published. The
heading and the flow keys are written in the file's language, with the words of base's ``workbook`` vocabulary, so the
only language this module names is the source's.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from django.utils.translation import pgettext_lazy

from base import catalog

#: The language WORKBOOK.md is written in; any other reads its own ``WORKBOOK.<language>.md`` while it is current.
SOURCE_LANGUAGE = "es"

SCREENS = pgettext_lazy("workbook", "Screens")
DONE = pgettext_lazy("workbook", "done")
KEYS = {
    "status": pgettext_lazy("workbook", "Status"),
    "vertical": pgettext_lazy("workbook", "Vertical"),
    "actor": pgettext_lazy("workbook", "Actor"),
    "screen": pgettext_lazy("workbook", "Screen"),
    "steps": pgettext_lazy("workbook", "Steps"),
    "in": pgettext_lazy("workbook", "In"),
    "out": pgettext_lazy("workbook", "Out"),
    "failure": pgettext_lazy("workbook", "If it fails"),
    "assistant": pgettext_lazy("workbook", "Through the assistant"),
    "involved": pgettext_lazy("workbook", "Involved"),
}

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FLOW = re.compile(r"^([A-Z][A-Z0-9_]*-F\d+)\s+(.+)$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_PARENTHESES = re.compile(r"\([^()]*\)")
_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class Words:
    """How a WORKBOOK in one language writes the screens heading, the flow keys (by field) and a flow that is done."""

    screens: str
    done: str
    keys: Mapping[str, str]


@dataclass(frozen=True)
class Tab:
    id: str
    label: str
    path: str


@dataclass(frozen=True)
class Screen:
    id: str
    title: str
    path: str
    text: str


@dataclass(frozen=True)
class Flow:
    id: str
    title: str
    screens: tuple[str, ...]
    steps: str
    failure: str


@dataclass(frozen=True)
class Help:
    purpose: str
    screens: tuple[Screen, ...]
    flows: tuple[Flow, ...]
    #: The ``###`` under the screens heading that name no tab.
    unknown_screens: tuple[str, ...]


def words() -> Words:
    """base's ``workbook`` vocabulary in the active language."""
    return Words(str(SCREENS), str(DONE), {field: str(word) for field, word in KEYS.items()})


def workbook(root: Path, language: str) -> tuple[str, str]:
    """The language served and the customer's part in it: ``WORKBOOK.<language>.md`` while its first line is the hash of
    the source's part (``catalog.en_header``), else the source's part of ``WORKBOOK.md``."""
    source = catalog.user_part((root / catalog.WORKBOOK).read_text(encoding="utf-8"))
    translated = root / f"WORKBOOK.{language}.md"
    if language == SOURCE_LANGUAGE or not _LANGUAGE.fullmatch(language) or not translated.is_file():
        return SOURCE_LANGUAGE, source
    header, _, body = translated.read_text(encoding="utf-8").partition("\n")
    if header.strip() != catalog.en_header(catalog.source_hash(source)):
        return SOURCE_LANGUAGE, source
    return language, body.strip("\n") + "\n"


def parse(markdown: str, tabs: Sequence[Tab], vocabulary: Words) -> Help:
    """The help of a customer's part written with ``vocabulary``, for a module whose tabs are ``tabs``."""
    sections = _sections(markdown.splitlines(), 2)[1:]
    purpose = _markdown(sections[0][1]) if sections else ""
    screens_heading = _name(vocabulary.screens)
    screen_lines = next((body for title, body in sections if _name(title) == screens_heading), [])
    screens, windows, unknown = _screens(screen_lines, tabs)
    places = {**windows, **{_name(tab.label): tab.id for tab in tabs}}
    flows = tuple(flow for _title, body in sections for flow in _flows(body, vocabulary, places))
    return Help(purpose, screens, flows, unknown)


def _screens(lines: list[str], tabs: Sequence[Tab]) -> tuple[tuple[Screen, ...], dict[str, str], tuple[str, ...]]:
    """The screen of each tab with a section, in the tabs' order; each window's name with its tab; the unknown titles."""
    by_name = {_name(tab.label): tab for tab in tabs}
    found: dict[str, list[str]] = {}
    unknown: list[str] = []
    for title, body in _sections(lines, 3)[1:]:
        tab = by_name.get(_name(title))
        if tab is None:
            unknown.append(title)
        else:
            found.setdefault(tab.id, body)
    screens = tuple(Screen(tab.id, tab.label, tab.path, _markdown(found[tab.id])) for tab in tabs if tab.id in found)
    windows = {_name(title): tab_id for tab_id, body in found.items() for title, _ in _sections(body, 4)[1:]}
    return screens, windows, tuple(unknown)


def _flows(lines: list[str], vocabulary: Words, places: dict[str, str]) -> Iterator[Flow]:
    """The flows of a section that are done on a tab (or one of its windows)."""
    for title, body in _sections(lines, 3)[1:]:
        heading = _FLOW.match(title)
        if heading is None:
            continue
        fields = _fields(body, vocabulary)
        screens = _places(fields.get("screen", []), places)
        if screens and _is_done(fields.get("status", []), vocabulary):
            steps, failure = _markdown(fields.get("steps", [])), _markdown(fields.get("failure", []))
            yield Flow(heading.group(1), heading.group(2).strip(), screens, steps, failure)


def _fields(lines: list[str], vocabulary: Words) -> dict[str, list[str]]:
    """The lines of each key of a flow (``<Key>: …`` at the start of a line, then every line until the next key)."""
    by_word = {word: field for field, word in vocabulary.keys.items()}
    key = re.compile(rf"^({'|'.join(re.escape(word) for word in by_word)}):[ \t]*(.*)$")
    fields: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        match = key.match(line)
        if match:
            current = fields.setdefault(by_word[match.group(1)], [])
            current.extend([match.group(2)] if match.group(2).strip() else [])
        elif current is not None:
            current.append(line)
    return fields


def _is_done(status: list[str], vocabulary: Words) -> bool:
    return _name(_without_parentheses(" ".join(status))) == _name(vocabulary.done)


def _places(screen: list[str], places: dict[str, str]) -> tuple[str, ...]:
    """The tabs a flow's screen names: its parts split on «,» and «;», what goes in parentheses left out."""
    found: list[str] = []
    for part in re.split(r"[,;]", _without_parentheses(" ".join(screen))):
        tab_id = places.get(_name(part))
        if tab_id is not None and tab_id not in found:
            found.append(tab_id)
    return tuple(found)


def _without_parentheses(text: str) -> str:
    while (inner := _PARENTHESES.sub("", text)) != text:
        text = inner
    return text


def _name(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def _sections(lines: list[str], level: int) -> list[tuple[str | None, list[str]]]:
    """``lines`` cut at each heading of ``level`` outside a code block: what goes before the first one (no title), then
    each heading's title with the lines under it."""
    prefix = "#" * level + " "
    parts: list[tuple[str | None, list[str]]] = [(None, [])]
    for line, code in zip(lines, _code_lines(lines), strict=True):
        if not code and line.startswith(prefix):
            parts.append((line[len(prefix) :].strip(), []))
        else:
            parts[-1][1].append(line)
    return parts


def _code_lines(lines: list[str]) -> list[bool]:
    """Whether each line belongs to a fenced code block, its fences included."""
    flags: list[bool] = []
    fence: str | None = None
    for line in lines:
        opening = _FENCE.match(line)
        flags.append(fence is not None or opening is not None)
        if fence is None:
            fence = opening.group(1) if opening else None
        elif set(stripped := line.strip()) == {fence[0]} and len(stripped) >= len(fence):
            fence = None
    return flags


def _markdown(lines: list[str]) -> str:
    """``lines`` as the window paints them: the indented lines that go on with a list item joined to it, since the
    screen ends an item at its first line, and the blank lines around them dropped."""
    out: list[str] = []
    in_item = False
    for line, code in zip(lines, _code_lines(lines), strict=True):
        if code or not line.strip():
            out.append(line.rstrip())
            in_item = False
        elif in_item and line[:1].isspace() and not _LIST_ITEM.match(line):
            out[-1] = f"{out[-1]} {line.strip()}"
        else:
            out.append(line.rstrip())
            in_item = _LIST_ITEM.match(line) is not None
    return "\n".join(out).strip("\n")
