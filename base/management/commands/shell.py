"""``manage.py shell``, in a database context (phase 2, S1; plan docs/plans/2026-10-22-fase-2-tenencia.md).

A hub's model without a context fails (``HubContextMissing``), so the shell runs on control (``use_control``: the
registry, the platform's outbox) or, with ``--hub <slug>``, in that hub's database (``use_hub``: the e2e's ``shell -c``
helpers relay a hub's outbox there). Since S5 there is no shared database: a business without its own is refused.
"""

from django.core.management import CommandError
from django.core.management.commands.shell import Command as DjangoShell

from base.registry import hub_by_slug
from base.tenancy.context import serves_hubs_without_database, use_control, use_hub


class Command(DjangoShell):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--hub", help="Work in this hub's database (its slug) instead of control's.")

    def handle(self, **options):
        slug = options.pop("hub", None)
        if not slug:
            with use_control():
                return super().handle(**options)
        hub = hub_by_slug(slug)
        if hub is None:
            raise CommandError(f"{slug!r} names no hub of the registry.")
        if not hub.db_name and not serves_hubs_without_database():
            raise CommandError(f"{slug} has no database of its own yet: manage.py cut_shared_hubs gives it one.")
        with use_hub(hub):
            return super().handle(**options)
