"""``manage.py qa_coverage [--ledger <csv>] [--assistant]``: which done flows of the WORKBOOKs the QA journeys walk, by
app, and with a ledger of walks (kept outside the repository), when the QA last walked each one, on a screen and through
the assistant; with ``--assistant``, what the assistant does in each one. The contract is ``qa/README.md``."""

from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from live.operations import registry

from base import catalog, qa_assistant, qa_coverage
from base.assistant.tools import is_tool

type Walks = dict[str, dict[str, qa_coverage.Walk]]

WAYS = {"screen": (qa_coverage.SCREEN,), "assistant": qa_coverage.ASSISTANT_CHANNELS}
LABELS = {"walked": "in a journey", "not_walked": "in none", "out_of_reach": "out of visual scope"}


class Command(BaseCommand):
    help = (
        "Which done flows of the WORKBOOKs the QA journeys walk, by app, and when each was last walked on a screen and"
        " through the assistant (--ledger). With --assistant, what the assistant does in each one."
    )

    def add_arguments(self, parser):
        parser.add_argument("--ledger", help="CSV of walks with the columns " + ",".join(qa_coverage.LEDGER_COLUMNS))
        parser.add_argument(
            "--assistant",
            action="store_true",
            help="What the assistant does in each flow done on a screen, and what is left to write in the WORKBOOKs.",
        )

    def handle(self, *args, ledger: str | None = None, assistant: bool = False, **options):
        root = Path(settings.BASE_DIR)
        walks = _walks(Path(ledger)) if ledger else None
        flows = qa_coverage.workbook_flows(root)
        journeys = qa_coverage.read_journeys(root, catalog.known_verticals())
        problems = [f"{journey.name}: {problem}" for journey in journeys for problem in journey.problems]
        for problem in [*problems, *qa_coverage.citation_problems(flows, journeys)]:
            self.stdout.write(f"! {problem}")
        report = qa_coverage.coverage(flows, journeys)
        for app, split in report.items():
            self.stdout.write(f"{app}: {_counts(split)}")
            for field, label in LABELS.items():
                if ids := getattr(split, field):
                    self.stdout.write(f"  {label}: {', '.join(ids)}")
        if walks is not None:
            self._write_walks(flows, walks)
        if assistant:
            self._write_assistant(qa_assistant.report(root, flows, registry))
        totals = qa_coverage.Coverage(*(sum((getattr(split, field) for split in report.values()), ()) for field in LABELS))
        self.stdout.write(f"total: {_counts(totals)}")

    def _write_walks(self, flows: dict[str, qa_coverage.WorkbookFlow], walks: Walks) -> None:
        """For the screens and then for the assistant, each walkable flow never walked there, then the last walks of the
        others from the longest ago."""
        walkable = [flow.id for flow in flows.values() if flow.walkable]
        for way, channels in WAYS.items():
            never = [flow_id for flow_id in walkable if not walks.get(flow_id, {}).keys() & set(channels)]
            self.stdout.write(f"last walks, {way}: {len(walkable) - len(never)} walked, {len(never)} never")
            for flow_id in never:
                self.stdout.write(f"  {flow_id} never")
            for flow_id, walk in _from_the_longest_ago(walkable, walks, channels):
                self.stdout.write(f"  {flow_id} {_described(walk)}")
        if unknown := sorted(walks.keys() - flows.keys()):
            self.stdout.write(f"  the ledger names flows in no WORKBOOK of the Hub: {', '.join(unknown)}")

    def _write_assistant(self, report: qa_assistant.Report) -> None:
        """What to expect of each flow when it is asked for by talking, and then what is left to write: the flows with
        no group, the ones that contradict themselves and the tools no flow cites."""
        groups = Counter(one.group for one in report.flows)
        counts = [f"{groups[group]} {group}" for group in qa_assistant.Group]
        self.stdout.write(f"assistant: {', '.join(counts)}, {groups[None]} undecided")
        for one in report.flows:
            if one.group is not None:
                self.stdout.write(f"  {one.flow.id} {one.group}: {one.expected}{_backing(one)}")
        undecided = [one.flow.id for one in report.flows if one.group is None]
        self._write_list("undecided, none of their operations is known", undecided)
        contradictory = [(kind, one.flow.id) for one in report.flows for kind in one.contradictions]
        self.stdout.write(f"contradictions: {len(contradictory)}")
        for kind in qa_assistant.Contradiction:
            self._write_list(f"  {kind}", [f"  {flow_id}" for found, flow_id in contradictory if found is kind])
        self._write_list("tools no flow cites", report.uncited_tools)

    def _write_list(self, title: str, items: Sequence[str]) -> None:
        self.stdout.write(f"{title}: {len(items)}")
        for item in items:
            self.stdout.write(f"  {item}")


def _backing(one: qa_assistant.Asked) -> str:
    """The operations of a flow, saying which are tools of the assistant."""
    names = [f"{op.name} (tool)" if is_tool(op) else op.name for op in one.operations]
    return f" — {', '.join(names)}" if names else ""


def _from_the_longest_ago(
    walkable: list[str], walks: Walks, channels: Iterable[str]
) -> list[tuple[str, qa_coverage.Walk]]:
    done = [
        (flow_id, walks[flow_id][channel])
        for flow_id in walkable
        for channel in channels
        if channel in walks.get(flow_id, {})
    ]
    return sorted(done, key=lambda one: one[1].date)


def _described(walk: qa_coverage.Walk) -> str:
    model = walk.model_result and f"model:{walk.model_result}"
    phrase = walk.phrase and f"phrase:{walk.phrase}"
    parts = (walk.channel, walk.date, walk.result, model, phrase, walk.device, walk.app_version, walk.issue)
    return " ".join(filter(None, parts))


def _walks(ledger: Path) -> Walks:
    try:
        return qa_coverage.last_walks(ledger)
    except (qa_coverage.LedgerError, OSError) as error:
        raise CommandError(f"Cannot read the ledger: {error}") from error


def _counts(split: qa_coverage.Coverage) -> str:
    return ", ".join(f"{len(getattr(split, field))} {label}" for field, label in LABELS.items())
