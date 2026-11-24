"""``manage.py qa_coverage [--ledger <csv>]``: which done flows of the WORKBOOKs the QA journeys walk, by app, and with a
ledger of walks (kept outside the repository), when the QA last walked each one, on a screen and through the assistant.
The contract is ``qa/README.md``."""

from collections.abc import Iterable
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from base import catalog, qa_coverage

type Walks = dict[str, dict[str, qa_coverage.Walk]]

WAYS = {"screen": (qa_coverage.SCREEN,), "assistant": qa_coverage.ASSISTANT_CHANNELS}
LABELS = {"walked": "in a journey", "not_walked": "in none", "out_of_reach": "out of visual scope"}


class Command(BaseCommand):
    help = (
        "Which done flows of the WORKBOOKs the QA journeys walk, by app, and when each was last walked on a screen and"
        " through the assistant (--ledger)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--ledger", help="CSV of walks with the columns " + ",".join(qa_coverage.LEDGER_COLUMNS))

    def handle(self, *args, ledger: str | None = None, **options):
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
