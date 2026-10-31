"""``manage.py migrate_hubs``: the ``hub-migrate`` task of every deploy (aws-next README, «Contrato»; PLAN-DB §7).

1. The control database, under its lock (``base.tenancy.migrator.migrate_control``).
2. The templates, as canaries, on every server the hubs live on (``clusters_to_migrate``: ``CREATE DATABASE …
   TEMPLATE`` clones only within one): ``hub_template`` and one ``hub_template_<vertical>`` per vertical, created if
   missing and brought up to date, never rebuilt. One that fails stops the run before any hub.
3. Every hub behind (``Hub.schema_apps``), through its own server: ERPlora's own first, then at most
   ``migrator.HUB_WORKERS`` at once. One that fails is marked ``behind`` and the others go on.

Any failure is logged with its traceback and exits non-zero, which the infra's ``task_failed`` rule reports.

``--check`` applies nothing, as ``migrate --check``: it lists what a run would apply (one ``<app>.<migration>`` per
line, under the database it belongs to; the hubs behind as ``<slug> (<database>)``) and exits 1 if anything; the
e2e's ``global-setup.ts`` runs it. It opens the templates, never a hub's database.
"""

import logging
import sys

from django.core.management.base import BaseCommand, CommandError

from base.tenancy import migrator

logger = logging.getLogger(__name__)


def _on(target) -> str:
    return f" on cluster {target.name}" if target.name else ""


class Command(BaseCommand):
    help = "Migrate the control database, then the templates of every server, then the hubs behind."

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
            raise CommandError(f"migrate_hubs: the control database was not migrated: {error}") from error
        self.stdout.write(f"migrate_hubs: control database migrated, {applied} migration(s) applied.")
        self.migrate_templates()
        self.migrate_hubs()

    def migrate_templates(self) -> None:
        try:
            plan = [
                (target, template)
                for target in migrator.clusters_to_migrate()
                for template in migrator.templates(target.control)
            ]
        except Exception as error:
            logger.exception("migrate_hubs: the clusters and their templates could not be read.")
            raise CommandError(f"migrate_hubs: the clusters and their templates could not be read: {error}") from error
        for target, template in plan:
            try:
                applied = migrator.ensure_template(template, target=target)
            except Exception as error:
                logger.exception("migrate_hubs: the template %s%s was not migrated.", template.db_name, _on(target))
                raise CommandError(
                    f"migrate_hubs: the template {template.db_name}{_on(target)} was not migrated: {error}; "
                    "no hub was touched."
                ) from error
            if applied:
                self.stdout.write(
                    f"migrate_hubs: template {template.db_name}{_on(target)}: {len(applied)} migration(s) applied."
                )
            else:
                self.stdout.write(f"migrate_hubs: template {template.db_name}{_on(target)} up to date.")
            if template.left_out:
                self.stdout.write(
                    f"migrate_hubs: template {template.db_name}{_on(target)} leaves out "
                    f"{', '.join(template.left_out)}: its tables reference a model of control's database."
                )

    def migrate_hubs(self) -> None:
        try:
            result = migrator.migrate_hubs_behind()
        except Exception as error:
            logger.exception("migrate_hubs: the hubs' pass did not run.")
            raise CommandError(f"migrate_hubs: the hubs' pass did not run: {error}") from error
        self.stdout.write(
            f"migrate_hubs: hubs: {len(result.migrated)} migrated, {len(result.failed)} left behind, "
            f"{result.up_to_date} up to date."
        )
        if result.failed:
            reasons = "; ".join(f"{slug} ({reason})" for slug, reason in result.failed.items())
            raise CommandError(f"migrate_hubs: {len(result.failed)} hub(s) left behind: {reasons}")

    def check_pending(self) -> None:
        try:
            pending = migrator.pending_control()
            templates = [
                (template, target, migrator.database_exists(template.db_name, target=target))
                for target in migrator.clusters_to_migrate()
                for template in migrator.templates(target.control)
            ]
            templates = [
                (template, target, exists, migrator.pending_template(template, target=target))
                for template, target, exists in templates
            ]
            every = migrator.hubs_with_a_database()
            code = migrator.code_migrations()
            behind = [hub for hub in every if migrator.is_behind(hub, code)]
        except Exception as error:
            logger.exception("migrate_hubs --check: the databases could not be read.")
            raise CommandError(f"migrate_hubs --check: the databases could not be read: {error}") from error
        lines = []
        if pending:
            lines += ["migrate_hubs: unapplied migrations in the control database:", *pending]
        for template, target, exists, missing in templates:
            if not missing:
                continue
            if exists:
                lines += [f"migrate_hubs: unapplied migrations in {template.db_name}{_on(target)}:", *missing]
            elif template.source is None:
                where = migrator.server_of(target)
                lines.append(f"migrate_hubs: {template.db_name} does not exist on {where}: run db-bootstrap there.")
            else:
                clones = f"a run clones it from {template.source} and applies:"
                lines += [f"migrate_hubs: {template.db_name}{_on(target)} does not exist; {clones}", *missing]
        if behind:
            lines += ["migrate_hubs: hubs behind the code:", *(f"{hub.slug} ({hub.db_name})" for hub in behind)]
        if not lines:
            self.stdout.write(
                f"migrate_hubs: the control database, {len(templates)} template(s) and {len(every)} hub(s) are "
                "up to date."
            )
            return
        for line in lines:
            self.stdout.write(line)
        sys.exit(1)
