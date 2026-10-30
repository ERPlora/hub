"""``manage.py seed_local_hubs``: the local hubs ``a`` and ``b``, ready in the registry (plan 2026-10-17, §1.3), with
every app on and its roots chosen, as every hub of before round 2026-10-27 (a business is born with every app off);
the apps of a local hub that already turned some on or off stay as they are.

The host gate (``base.middleware``) answers 404 to a slug without a row in the registry (``base.Hub``), so a
developer's database needs ``a`` and ``b`` (``a.localhost:8000``, ``b.localhost:8000``) once, after ``migrate``.
Local development only (``DEBUG``): production's hubs are the SaaS's, registered by ``PUT /internal/hubs/{id}``.
Idempotent, through its operation (``base.hub.seed_local``). ``--check`` writes nothing and fails unless both are
ready (``base.hub.by_slugs``): the e2e's global setup asks it before the first spec.

Where their data lives (round 2026-10-30 of PLAN-DB, S2a) follows what can live in a hub's own database
(``base.tenancy.provision.portable_apps``): ``a`` and ``b`` turn every app on, so while some app cannot (its tables
refer to control's users), new ones share control's database and the log says which apps hold them there; the day every
app can, new ones are born with their own (``<control>_<hex>``), made here at once from ``<control>_template`` with
every app's tables and every app on, under their ``hub_due`` lease (``migrate_hubs`` makes the template first). A
local hub that already exists keeps the database it has.
"""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from live.context import system_context

from base import services
from base.queries import hubs_by_slugs
from base.registry import REGISTRY_SCOPE
from base.schemas import HubsBySlugIn, HubSeedLocalIn
from base.services import hub_seed_local
from base.tenancy import provision

logger = logging.getLogger(__name__)

LOCAL_HUBS = ("a", "b")
OUTCOMES = {
    "created": "created",
    "ready_again": "ready again",
    "already_ready": "already ready",
    "requested": "requested",
}


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
        every_app = provision.hub_app_labels()
        blocked = sorted(every_app - provision.portable_apps())
        if blocked:
            logger.warning(
                "base.seed_local_hubs.shared_database: a and b share the control database: %s cannot have their "
                "tables in a hub's own database yet (they refer to control's users).",
                ", ".join(blocked),
            )
            self.stdout.write(f"a and b share the control database ({len(blocked)} app(s) cannot live in their own yet).")
        answer = hub_seed_local(ctx, HubSeedLocalIn(slugs=list(LOCAL_HUBS), own_database=not blocked))
        for seeded in answer.hubs:
            said = OUTCOMES[seeded.outcome]
            hub = services.registry_row_by_slug(seeded.slug)
            if hub.db_name and hub.status != hub.Status.READY:
                if not provision.provision(hub, apps=every_app, seed=services.turn_every_app_on, tell_saas=False):
                    failed = services.registry_row_by_slug(seeded.slug)
                    raise CommandError(
                        f"{seeded.slug}: its own database could not be made ({failed.status}: "
                        f"{failed.last_error or 'held by another process'}). Run `manage.py migrate_hubs` "
                        "(it makes the template) and this command again."
                    )
                said = f"{said} (its own database)" if seeded.outcome != "already_ready" else said
            self.stdout.write(f"{seeded.slug}: {said}")
