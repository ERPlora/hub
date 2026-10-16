"""``manage.py migrate_hubs``: the ``hub-migrate`` task of every deploy (aws-next README, «Contrato»).

Control → templates → hubs behind, each step under its lock (``base.tenancy.migrator``). Phase 1 has
no hub databases, so it migrates the control database only. Any failure is logged with its
traceback and exits non-zero, which the infra's ``task_failed`` rule reports.

``--check`` applies nothing, as ``migrate --check``: it lists, one ``<app>.<migration>`` per line,
what a run would apply and exits 1 if anything; the e2e's ``global-setup.ts`` runs it.
"""

import logging
import sys

from django.core.management.base import BaseCommand, CommandError

from base.tenancy import migrator

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Migrate the control database, then the templates and the hubs (phase 1: control only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Apply nothing; exit 1 and list them if any migration is unapplied.",
        )

    def handle(self, *args, check: bool = False, verbosity: int = 1, **options):
        if check:
            self.check_pending()
            return
        try:
            applied = migrator.migrate_control(stdout=self.stdout, verbosity=verbosity)
        except Exception as error:
            logger.exception("migrate_hubs: the control database was not migrated.")
            raise CommandError(
                f"migrate_hubs: the control database was not migrated: {error}"
            ) from error
        self.stdout.write(
            f"migrate_hubs: control database migrated, {applied} migration(s) applied "
            "(phase 1: no hub databases yet)."
        )

    def check_pending(self) -> None:
        try:
            pending = migrator.pending_control()
        except Exception as error:
            logger.exception("migrate_hubs --check: the control database could not be read.")
            raise CommandError(
                f"migrate_hubs --check: the control database could not be read: {error}"
            ) from error
        if not pending:
            self.stdout.write(
                "migrate_hubs: the control database is up to date (phase 1: no hub databases yet)."
            )
            return
        self.stdout.write("migrate_hubs: unapplied migrations in the control database:")
        for name in pending:
            self.stdout.write(name)
        sys.exit(1)
