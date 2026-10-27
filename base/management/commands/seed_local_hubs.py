"""``manage.py seed_local_hubs``: the local hubs ``a`` and ``b``, ready in the registry (plan 2026-10-17, §1.3), with
every app on and its roots chosen, as every hub of before round 2026-10-27 (a business is born with every app off);
the apps of a local hub that already turned some on or off stay as they are.

The host gate (``base.middleware``) answers 404 to a slug without a row in the registry (``base.Hub``), so a
developer's database needs ``a`` and ``b`` (``a.localhost:8000``, ``b.localhost:8000``) once, after ``migrate``.
Local development only (``DEBUG``): production's hubs are the SaaS's, registered by ``PUT /internal/hubs/{id}``.
Idempotent, through its operation (``base.hub.seed_local``). ``--check`` writes nothing and fails unless both are
ready (``base.hub.by_slugs``): the e2e's global setup asks it before the first spec.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from live.context import system_context

from base.queries import hubs_by_slugs
from base.registry import REGISTRY_SCOPE
from base.schemas import HubsBySlugIn, HubSeedLocalIn
from base.services import hub_seed_local

LOCAL_HUBS = ("a", "b")
OUTCOMES = {"created": "created", "ready_again": "ready again", "already_ready": "already ready"}


class Command(BaseCommand):
    help = "Leave the local hubs a and b ready in the registry (local development only; idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Write nothing; fail unless a and b are ready in the registry.",
        )

    def handle(self, *args, check: bool = False, **options):
        if not settings.DEBUG:
            raise CommandError("seed_local_hubs is for local development only (DEBUG=True). Nothing was written.")
        ctx = system_context(REGISTRY_SCOPE)
        if check:
            found = hubs_by_slugs(ctx, HubsBySlugIn(slugs=list(LOCAL_HUBS))).hubs
            missing = [f"{hub.slug} ({hub.status or 'missing'})" for hub in found if hub.status != "ready"]
            if missing:
                raise CommandError(
                    f"Not ready in the registry: {', '.join(missing)}. Run `manage.py seed_local_hubs`."
                )
            for hub in found:
                self.stdout.write(f"{hub.slug}: ready")
            return
        answer = hub_seed_local(ctx, HubSeedLocalIn(slugs=list(LOCAL_HUBS)))
        for hub in answer.hubs:
            self.stdout.write(f"{hub.slug}: {OUTCOMES[hub.outcome]}")
