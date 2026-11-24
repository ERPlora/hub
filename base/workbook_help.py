"""A module's help window, read from the customer's part of its WORKBOOK in one language.

The window only paints markdown. What it paints is cut here: what the module is for (what the first section says before
its first ``###``; from there on, who uses it and what it does not do stay in the file), the summary of each tab (what
its ``###`` under the screens heading, named as its tab, says before its first ``####``; each ``####`` is a window
inside the tab, written for whoever maintains the module, and only its title counts here, as a place where a flow is
done) and the flows that are done on one of those tabs, of which only the title, the steps and what happens if
they fail are published. The heading and the flow keys are written in the file's language, with the words of base's ``workbook``
vocabulary, so the only language this module names is the source's.
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
#: A line that is a block of its own: a heading, a quote, a table row or a rule.
_BLOCK = re.compile(r"^ {0,3}(?:#{1,6}(?:\s|$)|>|\|)")
_RULE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
#: Markdown's hard line break at the end of a line: two spaces or a backslash.
_HARD_BREAK = re.compile(r"(?:  |\\)$")
_PARENTHESES = re.compile(r"\([^()]*\)")
#: What starts the note a status may carry after its word: a dash, a colon or a parenthesis.
_STATUS_NOTE = re.compile(r"[(:—–]|\s-\s")
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
class Draft:
    """A flow that is not published: its status as written and the tabs its screen names."""

    id: str
    status: str
    screens: tuple[str, ...]


@dataclass(frozen=True)
class Help:
    purpose: str
    screens: tuple[Screen, ...]
    flows: tuple[Flow, ...]
    #: The ``###`` under the screens heading that name no tab, and those that name a tab already written.
    unknown_screens: tuple[str, ...]
    repeated_screens: tuple[str, ...]
    unpublished: tuple[Draft, ...]


def words() -> Words:
    """base's ``workbook`` vocabulary in the active language."""
    return Words(str(SCREENS), str(DONE), {field: str(word) for field, word in KEYS.items()})


def workbook(root: Path, language: str) -> tuple[str, str]:
    """The language served and the customer's part in it: ``WORKBOOK.<language>.md`` while its first line is the hash of
    the source's part (``catalog.en_header``), else the file of its base language (``en`` for ``en-gb``), else the
    source's part of ``WORKBOOK.md``."""
    source = catalog.user_part((root / catalog.WORKBOOK).read_text(encoding="utf-8"))
    header = catalog.en_header(catalog.source_hash(source))
    for candidate in dict.fromkeys((language, language.split("-")[0])):
        if candidate == SOURCE_LANGUAGE:
            break
        path = root / catalog.WORKBOOK_TRANSLATION.format(candidate)
        body = _current(path, header) if _LANGUAGE.fullmatch(candidate) else None
        if body is not None:
            return candidate, body
    return SOURCE_LANGUAGE, source


def _current(path: Path, header: str) -> str | None:
    """The body of the translation at ``path`` while its first line is ``header``, else ``None``."""
    if not path.is_file():
        return None
    first, _, body = path.read_text(encoding="utf-8").partition("\n")
    return body.strip("\n") + "\n" if first.strip() == header else None


def parse(markdown: str, tabs: Sequence[Tab], vocabulary: Words) -> Help:
    """The help of a customer's part written with ``vocabulary``, for a module whose tabs are ``tabs``."""
    sections = _sections(markdown.splitlines(), 2)[1:]
    purpose = _markdown(_sections(sections[0][1], 3)[0][1]) if sections else ""
    screens_heading = _name(vocabulary.screens)
    screen_lines = next((body for title, body in sections if _name(title) == screens_heading), [])
    screens, windows, unknown, repeated = _screens(screen_lines, tabs)
    places = {**windows, **{_place(tab.label): tab.id for tab in tabs}}
    read = [_flow(*flow, vocabulary, places) for flow in flow_fields(markdown, vocabulary)]
    flows = tuple(flow for flow in read if isinstance(flow, Flow))
    drafts = tuple(flow for flow in read if isinstance(flow, Draft))
    return Help(purpose, screens, flows, unknown, repeated, drafts)


def _screens(
    lines: list[str], tabs: Sequence[Tab]
) -> tuple[tuple[Screen, ...], dict[str, str], tuple[str, ...], tuple[str, ...]]:
    """The screen of each tab with a section, in the tabs' order (its first section, when written twice), whose text is
    its summary: what goes before its first window (``####``); each window's name with its tab; the titles that name no
    tab; and those of a tab already written."""
    by_name = {_name(tab.label): tab for tab in tabs}
    found: dict[str, list[str]] = {}
    unknown: list[str] = []
    repeated: list[str] = []
    for title, body in _sections(lines, 3)[1:]:
        tab = by_name.get(_name(title))
        if tab is None:
            unknown.append(title)
        elif tab.id in found:
            repeated.append(title)
        else:
            found[tab.id] = body
    cut = {tab_id: _sections(body, 4) for tab_id, body in found.items()}
    screens = tuple(Screen(tab.id, tab.label, tab.path, _markdown(cut[tab.id][0][1])) for tab in tabs if tab.id in cut)
    windows = {_place(title): tab_id for tab_id, parts in cut.items() for title, _ in parts[1:]}
    return screens, windows, tuple(unknown), tuple(repeated)


def flow_fields(markdown: str, vocabulary: Words) -> Iterator[tuple[str, str, dict[str, list[str]]]]:
    """Each flow of a customer's part written with ``vocabulary``, in the file's order: its id, its title and the lines
    of each of its keys."""
    for _title, body in _sections(markdown.splitlines(), 2)[1:]:
        for title, lines in _sections(body, 3)[1:]:
            if heading := _FLOW.match(title):
                yield heading.group(1), heading.group(2).strip(), _fields(lines, vocabulary)


def _flow(
    flow_id: str, title: str, fields: dict[str, list[str]], vocabulary: Words, places: dict[str, str]
) -> Flow | Draft:
    """A flow published when it is done on a tab (or one of its windows), else a draft."""
    status = " ".join(line.strip() for line in fields.get("status", [])).strip()
    screens = _places(fields.get("screen", []), places)
    if screens and is_done(status, vocabulary):
        steps, failure = (_capital(_markdown(fields.get(key, []))) for key in ("steps", "failure"))
        return Flow(flow_id, title, screens, steps, failure)
    return Draft(flow_id, status, screens)


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


def is_done(status: str, vocabulary: Words) -> bool:
    """Whether ``status``, before the note it may carry, is the word of a flow that is done."""
    return _name(_STATUS_NOTE.split(status, maxsplit=1)[0]) == _name(vocabulary.done)


def _places(screen: list[str], places: dict[str, str]) -> tuple[str, ...]:
    """The tabs a flow's screen names: its parts split on «,» and «;», what goes in parentheses left out."""
    found: list[str] = []
    for part in re.split(r"[,;]", _without_parentheses(" ".join(screen))):
        tab_id = places.get(_place(part))
        if tab_id is not None and tab_id not in found:
            found.append(tab_id)
    return tuple(found)


def _without_parentheses(text: str) -> str:
    while (inner := _PARENTHESES.sub("", text)) != text:
        text = inner
    return text


def _name(text: str | None) -> str:
    return " ".join((text or "").split()).casefold()


def _place(text: str) -> str:
    """How a flow's screen and a tab's or a window's name are compared: what goes in parentheses left out."""
    return _name(_without_parentheses(text))


def _capital(text: str) -> str:
    """``text`` with its first character in capitals: a lower-case letter's, since a list's number, a backtick or a
    quotation mark have none."""
    return text[:1].upper() + text[1:]


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
    """``lines`` as the window paints them, which keeps every line break: a paragraph or a list item that the file wraps
    over several lines becomes one line, unless a line ends in a hard break (two spaces or a backslash, which then goes);
    headings, quotes, tables, rules and code stay as they are, and the blank lines around them all go."""
    out: list[str] = []
    joinable = False
    for line, code in zip(lines, _code_lines(lines), strict=True):
        kind = _kind(line, code)
        if kind == "text" and joinable:
            out[-1] = f"{out[-1]} {line.strip()}"
        else:
            out.append(line.rstrip())
        joinable = kind != "block" and not _HARD_BREAK.search(line)
        if kind != "block" and not joinable:
            out[-1] = out[-1].removesuffix("\\")
    return "\n".join(out).strip("\n")


def _kind(line: str, code: bool) -> str:
    """``block`` (code, a blank line, a heading, a quote, a table row or a rule), ``item`` or ``text``."""
    if code or not line.strip() or _BLOCK.match(line) or _RULE.match(line):
        return "block"
    return "item" if _LIST_ITEM.match(line) else "text"
