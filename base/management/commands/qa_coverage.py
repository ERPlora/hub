"""``manage.py qa_coverage [--ledger <csv>]``: which done flows of the WORKBOOKs the QA journeys walk, by app, and with a
ledger of walks (kept outside the repository), when the QA last walked each one. The contract is ``qa/README.md``."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from base import catalog, qa_coverage

LABELS = {"walked": "in a journey", "not_walked": "in none", "out_of_reach": "out of visual scope"}


class Command(BaseCommand):
    help = "Which done flows of the WORKBOOKs the QA journeys walk, by app, and when each was last walked (--ledger)."

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

    def _write_walks(self, flows: dict[str, qa_coverage.WorkbookFlow], walks: dict[str, qa_coverage.Walk]) -> None:
        """Each walkable flow the ledger never names, then the others from the longest ago walked."""
        self.stdout.write("last walks:")
        walkable = [flow.id for flow in flows.values() if flow.walkable]
        for flow_id in (flow_id for flow_id in walkable if flow_id not in walks):
            self.stdout.write(f"  {flow_id} never")
        for flow_id in sorted((flow_id for flow_id in walkable if flow_id in walks), key=lambda one: walks[one].date):
            walk = walks[flow_id]
            line = f"  {flow_id} {walk.date} {walk.result} {walk.device} {walk.app_version} {walk.issue}"
            self.stdout.write(line.rstrip())
        if unknown := sorted(walks.keys() - flows.keys()):
            self.stdout.write(f"  the ledger names flows no WORKBOOK has: {', '.join(unknown)}")


def _walks(ledger: Path) -> dict[str, qa_coverage.Walk]:
    try:
        return qa_coverage.last_walks(ledger)
    except (qa_coverage.LedgerError, OSError) as error:
        raise CommandError(f"Cannot read the ledger: {error}") from error


def _counts(split: qa_coverage.Coverage) -> str:
    return ", ".join(f"{len(getattr(split, field))} {label}" for field, label in LABELS.items())
