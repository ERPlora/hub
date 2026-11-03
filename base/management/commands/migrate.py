"""``manage.py migrate``, refused on any alias but control's (PLAN-DB §4 «Comandos» and §14.9; plan 2026-10-22, §2.7).

``migrate`` migrates the control database (since S5 only control's tables and the outbox); the ``shared`` alias is the
SaaS's and migrates nothing (``base.routers.SharedRouter``). A hub's database, a demo's or a template's changes only
through the migrator (``base.tenancy.migrator``), which creates just the apps that hub has: ``migrate`` on its alias
would create them all, so it is refused before touching it.
"""

from django.core.management import CommandError
from django.core.management.commands.migrate import Command as DjangoMigrate
from django.db import DEFAULT_DB_ALIAS

from base.routers import SHARED_ALIAS

#: The aliases ``migrate`` takes.
MIGRATABLE_ALIASES = frozenset({DEFAULT_DB_ALIAS, SHARED_ALIAS})


class Command(DjangoMigrate):
    def handle(self, *args, **options):
        database = options["database"]
        if database not in MIGRATABLE_ALIASES:
            raise CommandError(
                f"migrate works on the control database only, not on {database!r}: a hub's schema changes through "
                "the migrator (base.tenancy.migrator, manage.py migrate_hubs)."
            )
        return super().handle(*args, **options)
