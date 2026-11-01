"""``manage.py cut_shared_hubs``: the cut of S5, each business of phase 1 given its own database
(``base.tenancy.cut``; runbook ``docs/runbooks/cut-shared-hubs.md``).

Each business still on control's database (``db_name`` empty) is named with its mode: ``--copy-all <slug>`` (one,
once: every row control's tables of the hubs' apps hold goes into it), ``--recreate <slug>`` (its database from its
template and the SaaS's photo, nothing copied) or ``--skip <slug>`` (a cancelled one, left without a database). The
plan is printed first, a business with each mode, the tables and rows a copy takes; ``--dry-run`` stops there and
writes nothing. Before the first cut, control is copied to the dumps bucket (``<control>/<time>-cut.dump``): without
a bucket it is refused unless ``--no-dump`` (local development and ``pre`` only). The businesses are cut one at a
time, the copy first; the first that fails stops the run with why, left as it was, and the next run does it again.
A business already with its own database is left as it is. Runs where the migrator's credentials are (the
``hub-migrate`` task in AWS).
"""

from django.core.management.base import BaseCommand, CommandError

from base import services
from base.tenancy import cut, dumps
from base.tenancy import connections as tenancy_connections
from base.tenancy.context import use_control
from control.models import Hub


class Command(BaseCommand):
    help = (
        "Give each business still on control's database its own: --copy-all <slug> (once), --recreate <slug> or "
        "--skip <slug> (a cancelled one). --dry-run prints the plan and writes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print what each business would get; write nothing.")
        parser.add_argument(
            "--copy-all",
            dest="copy_all",
            default=None,
            metavar="SLUG",
            help="The one business that gets every row of control's tables of the hubs' apps (once).",
        )
        parser.add_argument(
            "--recreate",
            action="append",
            default=[],
            metavar="SLUG",
            help="A business made again from its template and the SaaS's photo, nothing copied.",
        )
        parser.add_argument(
            "--skip", action="append", default=[], metavar="SLUG", help="A cancelled business, left without a database."
        )
        parser.add_argument(
            "--no-dump",
            action="store_true",
            help="Cut without copying control to the dumps bucket first (local development and pre only).",
        )

    def handle(self, *args, dry_run=False, copy_all=None, recreate=(), skip=(), no_dump=False, **options):
        modes = self._modes(copy_all, recreate, skip)
        with use_control():
            on_control = services.hubs_on_control()
            refusals = self._refusals(modes)
            self._print_plan(on_control, modes, no_dump)
        for line in refusals:
            self.stdout.write(f"Refused: {line}")
        if dry_run:
            self.stdout.write("Dry run: nothing was written.")
            return
        if refusals:
            raise CommandError("Nothing was cut:\n" + "\n".join(f"- {line}" for line in refusals))
        if not modes:
            raise CommandError("There is no business to cut: name each with --copy-all, --recreate or --skip.")
        with use_control():
            rows = {slug: services.registry_row_by_slug(slug) for slug in modes}
        to_cut = [
            slug
            for slug in sorted(modes, key=lambda slug: (modes[slug] != cut.COPY_ALL, slug))
            if modes[slug] != cut.SKIP and not rows[slug].db_name
        ]
        dump = ""
        if to_cut and not no_dump:
            try:
                dump = dumps.dump_control(kind=dumps.CUT)
            except dumps.DumpsUnavailable as missing:
                raise CommandError(
                    f"{missing} Control is copied before the first cut: set HUB_DUMPS_BUCKET, or pass --no-dump "
                    "(local development and pre only)."
                ) from missing
            except dumps.DumpFailed as failed:
                raise CommandError(f"Control could not be copied, nothing was cut: {failed}") from failed
            self.stdout.write(f"Control copied to s3://{dumps.bucket()}/{dump}")
        for slug in sorted(modes):
            if rows[slug].db_name:
                self.stdout.write(f"{slug}: already has its own database ({rows[slug].db_name}), left as it is.")
            elif modes[slug] == cut.SKIP:
                self.stdout.write(f"{slug}: skipped, without a database (base.hub.restore makes one if it comes back).")
        for slug in to_cut:
            try:
                outcome = cut.cut_hub(rows[slug].id, modes[slug], dump=dump)
            except cut.CutError as error:
                raise CommandError(f"{slug}: the cut failed and it was left on control's database: {error}") from error
            self.stdout.write(
                f"{slug}: {cut.MODE_NAMES[outcome.mode]} done in {outcome.seconds:.1f} s, database "
                f"{outcome.database}, {sum(outcome.copied.values())} rows copied."
            )

    @staticmethod
    def _modes(copy_all, recreate, skip) -> dict[str, str]:
        named = [(slug, cut.COPY_ALL) for slug in ([copy_all] if copy_all else [])]
        named += [(slug, cut.RECREATE) for slug in recreate] + [(slug, cut.SKIP) for slug in skip]
        modes: dict[str, str] = {}
        for slug, mode in named:
            if slug in modes:
                raise CommandError(f"{slug} is named more than once: give each business one mode.")
            modes[slug] = mode
        return modes

    @staticmethod
    def _refusals(modes: dict[str, str]) -> list[str]:
        refusals = []
        went_to = services.copy_all_went_to()
        for slug, mode in sorted(modes.items()):
            hub = services.registry_row_by_slug(slug)
            if hub is None:
                refusals.append(f"{slug}: no business has this name.")
            elif hub.is_demo:
                refusals.append(f"{slug}: a demo is not cut, it ends on its own.")
            elif hub.db_name:
                continue
            elif mode == cut.SKIP and hub.status != Hub.Status.CANCELLED:
                refusals.append(f"{slug} is {hub.status}: only a cancelled business is skipped.")
            elif mode != cut.SKIP and hub.status != Hub.Status.READY:
                refusals.append(f"{slug} is {hub.status}: only a ready business is cut (skip a cancelled one).")
            elif mode == cut.COPY_ALL and went_to and went_to != slug:
                refusals.append(f"{slug}: control's rows already went to {went_to}; they are copied once.")
        return refusals

    def _print_plan(self, on_control: list[Hub], modes: dict[str, str], no_dump: bool) -> None:
        named = {hub.slug: hub for hub in on_control}
        for slug in modes:
            if slug not in named:
                found = services.registry_row_by_slug(slug)
                if found is not None:
                    named[slug] = found
        self.stdout.write(f"Businesses on control's database: {len(on_control)}")
        for slug in sorted(named):
            hub = named[slug]
            mode = modes.get(slug)
            head = f"- {slug} ({hub.status}): "
            if hub.db_name:
                self.stdout.write(head + f"already has its own database ({hub.db_name})")
            elif mode == cut.COPY_ALL:
                counted = cut.count_rows(slug)
                rows = {table: count for table, count in counted.items() if count}
                self.stdout.write(
                    head + f"copy-all, {sum(rows.values())} rows of {len(rows)} tables "
                    f"({len(counted) - len(rows)} empty)"
                )
                for table, count in sorted(rows.items()):
                    self.stdout.write(f"    {table}: {count}")
            elif mode == cut.RECREATE:
                self.stdout.write(head + "recreate, nothing copied")
            elif mode == cut.SKIP:
                self.stdout.write(head + "skip, no database is made")
            else:
                self.stdout.write(head + "no mode (name it with --copy-all, --recreate or --skip)")
        control = tenancy_connections.control_name()
        if no_dump:
            self.stdout.write("Control's copy before the first cut: none (--no-dump).")
        elif dumps.configured():
            self.stdout.write(
                f"Control's copy before the first cut: s3://{dumps.bucket()}/{control}/<time>-{dumps.CUT}.dump"
            )
        else:
            self.stdout.write("Control's copy before the first cut: refused, no HUB_DUMPS_BUCKET (or pass --no-dump).")
