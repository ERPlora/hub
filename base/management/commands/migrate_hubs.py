"""``manage.py migrate_hubs``: the ``hub-migrate`` task of every deploy (aws-next README, «Contrato»).

Control → templates → hubs behind, each step under its lock (``base.tenancy.migrator``). Phase 1 has
no hub databases, so it migrates the control database only. Any failure is logged with its
traceback and exits non-zero, which the infra's ``task_failed`` rule reports.
"""

import logging

from django.core.management.base import BaseCommand, CommandError

from base.tenancy import migrator

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Migrate the control database, then the templates and the hubs (phase 1: control only)."

    def handle(self, *args, verbosity: int = 1, **options):
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
