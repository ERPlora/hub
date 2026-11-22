"""``manage.py demo_expire <slug>``: end the demo ``<slug>`` now and purge it at once.

Support's tool (a demo to close by hand) and the e2e's clock (a demo that ended, without waiting an hour), in every
environment. All through operations: ``base.demo.expire`` (its host answers 410 from now on), its drop
(``base.tenancy.provision.drop_now``: its database and its files, then ``base.demo.purge``), then ``base.demo.get`` to
say how it was left. The worker may take the demo first, as soon as it ended: the command then waits for that drop
instead of saying the step it caught it in. A drop that fails is logged and left to the worker, which tries it again:
the command says the step it stayed in.

While the platform is frozen for a database upgrade (``control.freeze.set``) the demo ends all the same but its
database is left where it is (a ``DROP DATABASE`` would never reach the upgrade's copy): the worker's reaper drops it on
its first tick after the freeze is lifted, and the command says so.
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from live.context import system_context
from live.errors import NotFound

from base.queries.demos import demo_get
from base.registry import REGISTRY_SCOPE
from base.schemas.demos import DemoSlugIn
from base.services.demos import demo_expire
from base.services.provisioning import registry_row_by_slug
from base.tenancy import provision
from base.tenancy.context import use_control
from control.queries import active_freeze

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "End the demo <slug> now and purge it (its host answers 410 until its tombstone is forgotten)."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="The demo's address, demo-<8 hex>.")

    def handle(self, *args, slug: str, **options):
        ctx = system_context(REGISTRY_SCOPE)
        try:
            demo_expire(ctx, DemoSlugIn(slug=slug))
        except NotFound:
            raise CommandError(f"{slug!r} names no demo of this Hub. Nothing was changed.") from None
        with use_control():
            frozen = active_freeze() is not None
            demo = registry_row_by_slug(slug)
        if not frozen:
            try:
                provision.drop_now(demo)
            except Exception:
                logger.exception("base.demo.purge_failed demo=%s: the worker tries it again.", slug)
        status = demo_get(ctx, DemoSlugIn(slug=slug)).status
        if frozen:
            self.stdout.write(f"{slug}: {status} (frozen: its database is dropped once the freeze is lifted)")
            return
        self.stdout.write(f"{slug}: {status}")
