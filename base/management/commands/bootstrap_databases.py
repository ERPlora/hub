"""``manage.py bootstrap_databases``: the one-off ``db-bootstrap`` task (aws-next, «Contrato»).

Runs ``base.tenancy.bootstrap`` as the RDS master (``DB_NAME=postgres``) with the six
``*_PASSWORD`` of the roles: once before the first deploy, and again to rotate a password. One line
per step, never a password. A missing variable or a failed step exits non-zero (a
``CommandError``), which the infra's ``task_failed`` rule reports. In local mode (``DEBUG``) an
extension the server lacks (``vector`` of the template or of ``saas`` without pgvector) is a warning;
in production it fails. ``--prefix`` names every database and role apart: ``--prefix pre_`` is the pre environment
(``pre_hub``, ``pre_saas``, ``pre_hub_app``…, in prod's cluster; plan 2026-10-14-entorno-pre), and
any other prefix is for tests and rehearsals. Production runs without it.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from base.tenancy import bootstrap

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Create or converge the cluster's databases (saas, hub, hub_template) and roles, and set "
        "the roles' passwords from their *_PASSWORD variables. Idempotent; run as the RDS master."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--prefix",
            default="",
            help=(
                "Put this prefix in front of every database and role: pre_ for the pre environment, "
                "anything else for tests and rehearsals."
            ),
        )

    def handle(self, *args, prefix: str = "", **options):
        try:
            names = bootstrap.Names.with_prefix(prefix)
            passwords = bootstrap.read_passwords()
            steps = bootstrap.bootstrap(
                passwords=passwords,
                names=names,
                require_extensions=not settings.DEBUG,
                report=self._report,
            )
        except Exception as error:
            logger.exception("bootstrap_databases: the cluster was not bootstrapped.")
            raise CommandError(
                f"bootstrap_databases: the cluster was not bootstrapped: {error}"
            ) from error
        self.stdout.write(f"bootstrap_databases: done, {len(steps)} step(s).")

    def _report(self, step: bootstrap.Step) -> None:
        self.stdout.write(f"bootstrap_databases: {step}")
        if step.status == "skipped":
            self.stderr.write(
                self.style.WARNING(f"bootstrap_databases: WARNING {step}")
            )
