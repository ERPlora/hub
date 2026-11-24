"""Which flows of the WORKBOOKs the QA journeys walk, and when the QA last walked each one.

A journey, ``qa/journeys/<slug>.md``, is what a person does in one sitting across apps; each of its steps starts with
the ids of the flows it walks, so the WORKBOOKs stay the only description of what the Hub does (``qa/README.md``). A
flow is walkable when it is done and someone does it on a screen; the others are out of the journeys' reach.
"""

import csv
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from django.utils import translation

from base import catalog, workbook_help

JOURNEYS = Path("qa/journeys")
WORKBOOKS = ("base/WORKBOOK.md", "apps/*/WORKBOOK.md")
#: How a source WORKBOOK, written in Spanish, opens the screen of a flow no one does on one: «ninguna (se ve en …)».
NO_SCREEN = "ninguna"
ANY_VERTICAL = "any"
HEADER_FENCE = "---"
HEADER_KEYS = ("title", "vertical", "roles")
PURPOSE = "Para qué:"
START = "## Punto de partida"
STEPS = "## Recorrido"
SCREEN = "screen"
ASSISTANT_CHANNELS = ("assistant-es", "assistant-en")
CHANNELS = (SCREEN, *ASSISTANT_CHANNELS)
LEDGER_COLUMNS = ("flow", "date", "device", "app_version", "result", "issue", "channel", "phrase", "model_result")

_FLOW_ID = r"[A-Z][A-Z0-9_]*-F\d+"
_STEP = re.compile(rf"^(\d+)\. ({_FLOW_ID}(?:, {_FLOW_ID})*)(?: — \S.*)?$")
STEP_FORMAT = "«<n>. <FLOW-ID>[, <FLOW-ID>…][ — <note>]»"


class LedgerError(Exception):
    """A ledger of walks that cannot be read: a column is missing, a date is not ISO or a channel is not one."""


@dataclass(frozen=True)
class WorkbookFlow:
    id: str
    app: str
    done: bool
    on_screen: bool

    @property
    def walkable(self) -> bool:
        return self.done and self.on_screen


@dataclass(frozen=True)
class Journey:
    name: str
    vertical: str
    steps: tuple[tuple[str, ...], ...]
    problems: tuple[str, ...]


@dataclass(frozen=True)
class Coverage:
    walked: tuple[str, ...]
    not_walked: tuple[str, ...]
    out_of_reach: tuple[str, ...]


@dataclass(frozen=True)
class Walk:
    date: str
    device: str
    app_version: str
    result: str
    issue: str
    channel: str
    phrase: str
    model_result: str


def workbook_flows(root: Path) -> dict[str, WorkbookFlow]:
    """Every flow of the customer's part of the source WORKBOOKs under ``root``, by id."""
    with translation.override(workbook_help.SOURCE_LANGUAGE):
        vocabulary = workbook_help.words()
    flows: dict[str, WorkbookFlow] = {}
    for path in sorted(found for pattern in WORKBOOKS for found in root.glob(pattern)):
        markdown = catalog.user_part(path.read_text(encoding="utf-8"))
        for flow_id, _title, fields in workbook_help.flow_fields(markdown, vocabulary):
            done = workbook_help.is_done(" ".join(fields.get("status", [])), vocabulary)
            flows[flow_id] = WorkbookFlow(flow_id, path.parent.name, done, _on_screen(fields.get("screen", [])))
    return flows


def _on_screen(screen: list[str]) -> bool:
    first = " ".join(screen).split(maxsplit=1)
    return not first or first[0].strip(";,.:").casefold() != NO_SCREEN


def read_journeys(root: Path, verticals: Iterable[str]) -> list[Journey]:
    """Every journey of ``root``'s ``qa/journeys``, in the order of their names."""
    known = tuple(verticals)
    return [read_journey(path, known) for path in sorted((root / JOURNEYS).glob("*.md"))]


def read_journey(path: Path, verticals: Iterable[str]) -> Journey:
    """The journey at ``path`` and what breaks its format; its vertical is one of ``verticals`` or ``any``."""
    problems: list[str] = []
    header, body = _header(path.read_text(encoding="utf-8").splitlines(), problems)
    vertical = header.get("vertical", "")
    allowed = sorted({*verticals, ANY_VERTICAL})
    if vertical and vertical not in allowed:
        problems.append(f"vertical {vertical!r} is none of {', '.join(allowed)}")
    preamble, sections = _sections(body)
    if not any(line.startswith(PURPOSE) and line.removeprefix(PURPOSE).strip() for line in preamble):
        problems.append(f"no «{PURPOSE} …» line before its sections")
    titles = [title for title, _lines in sections]
    if titles != [START, STEPS]:
        problems.append(f"its sections are {titles}, not {[START, STEPS]}")
    parts = dict(sections)
    if not any(line.strip() for line in parts.get(START, [])):
        problems.append(f"«{START}» says nothing")
    steps = _steps(parts.get(STEPS, []), problems)
    return Journey(path.name, vertical, steps, tuple(problems))


def _header(lines: list[str], problems: list[str]) -> tuple[dict[str, str], list[str]]:
    """The ``key: value`` lines between the two ``---`` that open the file, and the lines after them."""
    if not lines or lines[0] != HEADER_FENCE or HEADER_FENCE not in lines[1:]:
        problems.append(f"it does not open with a header between two «{HEADER_FENCE}» lines")
        return {}, lines
    end = lines.index(HEADER_FENCE, 1)
    header: dict[str, str] = {}
    for line in lines[1:end]:
        key, colon, value = line.partition(":")
        if colon:
            header[key.strip()] = value.strip()
        else:
            problems.append(f"header line {line!r} is not «key: value»")
    problems.extend(f"the header has no {key}" for key in HEADER_KEYS if not header.get(key))
    return header, lines[end + 1 :]


def _sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """The lines before the first ``## `` heading, and each of those headings with the lines under it."""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("## "):
            sections.append((line.rstrip(), []))
        else:
            (sections[-1][1] if sections else preamble).append(line)
    return preamble, sections


def _steps(lines: list[str], problems: list[str]) -> tuple[tuple[str, ...], ...]:
    """The flow ids each step starts with; the steps are numbered from 1, one per line."""
    steps: list[tuple[str, ...]] = []
    for line in filter(str.strip, lines):
        match = _STEP.match(line)
        if match is None:
            problems.append(f"{line.strip()!r} is not a step {STEP_FORMAT}")
            continue
        if int(match.group(1)) != len(steps) + 1:
            problems.append(f"step {match.group(1)} should be number {len(steps) + 1}")
        steps.append(tuple(match.group(2).split(", ")))
    if not steps:
        problems.append("it has no steps")
    return tuple(steps)


def citation_problems(flows: Mapping[str, WorkbookFlow], journeys: Iterable[Journey]) -> list[str]:
    """Each flow a step cites that no WORKBOOK has or that is not done."""
    cited = (
        (f"{journey.name} step {number}: {flow_id}", flows.get(flow_id))
        for journey in journeys
        for number, step in enumerate(journey.steps, start=1)
        for flow_id in step
    )
    problems: list[str] = []
    for where, flow in cited:
        if flow is None:
            problems.append(f"{where} is in no WORKBOOK")
        elif not flow.done:
            problems.append(f"{where} is not done")
    return problems


def coverage(flows: Mapping[str, WorkbookFlow], journeys: Iterable[Journey]) -> dict[str, Coverage]:
    """Each app's flows, by app: the walkable ones a journey cites, the walkable ones none cites, and the others."""
    cited = {flow_id for journey in journeys for step in journey.steps for flow_id in step}
    split: dict[str, tuple[list[str], list[str], list[str]]] = {}
    for flow in flows.values():
        walked, not_walked, out_of_reach = split.setdefault(flow.app, ([], [], []))
        if not flow.walkable:
            out_of_reach.append(flow.id)
        elif flow.id in cited:
            walked.append(flow.id)
        else:
            not_walked.append(flow.id)
    return {app: Coverage(*(tuple(ids) for ids in lists)) for app, lists in sorted(split.items())}


def last_walks(path: Path) -> dict[str, dict[str, Walk]]:
    """The last walk of each flow on each channel in the ledger at ``path``: the one with its latest date there."""
    walks: dict[str, dict[str, Walk]] = {}
    with path.open(encoding="utf-8", newline="") as file:
        rows = csv.DictReader(file)
        missing = [column for column in LEDGER_COLUMNS if column not in (rows.fieldnames or ())]
        if missing:
            raise LedgerError(f"{path} has no column {', '.join(missing)}")
        for row in rows:
            walk = Walk(*(row[column] or "" for column in LEDGER_COLUMNS[1:]))
            _check_date(walk.date, path, rows.line_num)
            _check_channel(walk.channel, path, rows.line_num)
            by_channel = walks.setdefault(row["flow"], {})
            if walk.channel not in by_channel or walk.date >= by_channel[walk.channel].date:
                by_channel[walk.channel] = walk
    return walks


def _check_date(text: str, path: Path, line: int) -> None:
    """Refuse a date that is not written ``YYYY-MM-DD``: the latest walk is found by comparing the dates as text."""
    try:
        canonical = date.fromisoformat(text).isoformat() == text
    except ValueError:
        canonical = False
    if not canonical:
        raise LedgerError(f"{path} line {line}: {text!r} is not a date written YYYY-MM-DD")


def _check_channel(text: str, path: Path, line: int) -> None:
    if text not in CHANNELS:
        raise LedgerError(f"{path} line {line}: {text!r} is not a channel, one of {', '.join(CHANNELS)}")
