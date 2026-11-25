"""What the assistant does in each flow done on a screen, for the QA that asks for it by talking (``qa/README.md``).

The manuals already say which operations a flow uses (the «Flujos» column of their services tables) and the registry
which of those are tools of the assistant: the answer is worked out from both, and nothing here lists a flow.
"""

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from live.operations import Operation

from base import qa_coverage, workbook_help
from base.assistant.tools import is_tool
from base.qa_coverage import WorkbookFlow

#: How a source WORKBOOK, written in Spanish, heads its services tables and names the assistant.
FLOWS_COLUMN = "Flujos"
SERVICE_COLUMNS = ("Servicio", "Servicios", "Operación")
ASSISTANT = re.compile(r"\basistente\b", re.IGNORECASE)
#: No screen either: what a flow done through the assistant or the API names beside it.
API = "api"
#: The operations the assistant's own panel runs (a turn, its voice, a report): no tools, and they do back its flows.
PANEL = "base.assistant."

_CELL = re.compile(r"(?<!\\)\|")
_NAME = re.compile(r"`([^`]+)`")
_FLOWS = re.compile(r"(?:\b(?!F\d)([A-Z][A-Z0-9_]*)-)?\bF(\d+)(?:[-–]F(\d+))?")
_PLACE = re.compile(r"[,;]|\s[yo]\s")


class Group(StrEnum):
    CAN = "can"
    ASSISTANT_ONLY = "assistant only"
    CANNOT = "cannot"


EXPECTED = {
    Group.CAN: "does it; check it on the screen or in the data",
    Group.ASSISTANT_ONLY: "does it, and there is no other way; check it on the screen or in the data",
    Group.CANNOT: "says it does not do it and which screen does: {screen}",
}


@dataclass(frozen=True)
class Asked:
    """A flow asked for by talking; its group is ``None`` while none of its operations is known and it does not say it
    uses none, and it contradicts itself when it names the assistant and no tool backs it or when it says it uses no
    operation and one is cited."""

    flow: WorkbookFlow
    operations: tuple[Operation, ...]
    group: Group | None
    contradicts: bool

    @property
    def expected(self) -> str:
        return EXPECTED[self.group].format(screen=self.flow.screen) if self.group else ""


@dataclass(frozen=True)
class Report:
    flows: tuple[Asked, ...]
    uncited_tools: tuple[str, ...]


def report(root: Path, flows: Mapping[str, WorkbookFlow], operations: Mapping[str, Operation]) -> Report:
    """Each of ``flows`` done on a screen, as asked for by talking, and the tools of ``operations`` no flow cites."""
    cited = cited_operations(root)
    answers = tuple(
        asked(flow, [operations[name] for name in cited.get(flow.id, ()) if name in operations])
        for flow in flows.values()
        if flow.walkable
    )
    used = {name for flow_id in flows for name in cited.get(flow_id, ())}
    uncited = sorted(name for name, op in operations.items() if is_tool(op) and name not in used)
    return Report(answers, tuple(uncited))


def asked(flow: WorkbookFlow, operations: Sequence[Operation]) -> Asked:
    return Asked(flow, tuple(operations), _group(flow, operations), _contradicts(flow, operations))


def _group(flow: WorkbookFlow, operations: Sequence[Operation]) -> Group | None:
    if _only_the_assistant(flow.screen):
        return Group.ASSISTANT_ONLY
    if not operations:
        return Group.CANNOT if flow.no_operations else None
    writes = [op for op in operations if op.kind == "command"]
    can = any(map(is_tool, writes)) if writes else all(map(is_tool, operations))
    return Group.CAN if can else Group.CANNOT


def _only_the_assistant(screen: str) -> bool:
    """Whether the assistant is the only place ``screen`` names, what goes in parentheses left out."""
    named = (place.strip() for place in _PLACE.split(workbook_help.without_parentheses(screen)))
    places = [place for place in named if place and place.casefold() != API]
    return bool(places) and all(map(ASSISTANT.search, places))


def _contradicts(flow: WorkbookFlow, operations: Sequence[Operation]) -> bool:
    """Whether ``flow`` says it uses no operation and has some, or names the assistant with no tool behind it; as its
    screen, only against operations that are not its panel's: the panel is also where its own flows are done."""
    if flow.no_operations and operations:
        return True
    if any(map(is_tool, operations)):
        return False
    of_another_screen = bool(operations) and not any(op.name.startswith(PANEL) for op in operations)
    return bool(ASSISTANT.search(flow.actor) or (of_another_screen and ASSISTANT.search(flow.screen)))


def cited_operations(root: Path) -> dict[str, tuple[str, ...]]:
    """The names of the operations each flow uses, by its id, as the services tables of the WORKBOOKs under ``root``
    say: the rows that name the flow, in the order they are written."""
    cited: dict[str, dict[str, None]] = {}
    for path in qa_coverage.workbooks(root):
        for flows, services in _service_rows(path.read_text(encoding="utf-8").splitlines()):
            names = dict.fromkeys(_operation_names(services))
            for flow_id in _flow_ids(flows, path.parent.name.upper()):
                cited.setdefault(flow_id, {}).update(names)
    return {flow_id: tuple(names) for flow_id, names in cited.items()}


def _service_rows(lines: Sequence[str]) -> Iterator[tuple[str, str]]:
    """The flows cell and the services cell of each row of the tables that have both columns."""
    header: list[str] | None = None
    for line in lines:
        if not line.startswith("|"):
            header = None
            continue
        cells = [cell.strip() for cell in _CELL.split(line.strip())]
        if header is None:
            header = cells
            continue
        row = dict(zip(header, cells, strict=False))
        services = next((row[column] for column in SERVICE_COLUMNS if column in row), None)
        if services is not None and FLOWS_COLUMN in row:
            yield row[FLOWS_COLUMN], services


def _operation_names(services: str) -> Iterator[str]:
    """The names in backticks of a services cell; one written short, «`.update`», is of the entity of the one before."""
    entity = ""
    for written in _NAME.findall(services):
        name = entity + written if written.startswith(".") else written
        entity = name.rpartition(".")[0]
        yield name


def _flow_ids(flows: str, prefix: str) -> Iterator[str]:
    """The ids a flows cell names: «F01» is of the WORKBOOK's app and «F14–F17», every flow from one to the other."""
    for app, first, last in _FLOWS.findall(flows):
        for number in range(int(first), int(last or first) + 1):
            yield f"{app or prefix}-F{number:02d}"
