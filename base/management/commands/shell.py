"""``manage.py shell``, in a database context (phase 2, S1; plan docs/plans/2026-10-22-fase-2-tenencia.md).

A hub's model without a context fails (``HubContextMissing``), so the shell runs in phase 1's shared database, where
every hub with ``db_name=""`` keeps its data (``use_shared_database``, S1–S4: the e2e's ``shell -c`` helpers relay the
outbox there), or, with ``--hub <slug>``, in that hub's database (``use_hub``).
"""

from django.core.management import CommandError
from django.core.management.commands.shell import Command as DjangoShell

from base.registry import hub_by_slug
from base.tenancy.context import use_hub, use_shared_database


class Command(DjangoShell):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--hub", help="Work in this hub's database (its slug) instead of the shared one.")

    def handle(self, **options):
        slug = options.pop("hub", None)
        if not slug:
            with use_shared_database():
                return super().handle(**options)
        hub = hub_by_slug(slug)
        if hub is None:
            raise CommandError(f"{slug!r} names no hub of the registry.")
        with use_hub(hub):
            return super().handle(**options)
