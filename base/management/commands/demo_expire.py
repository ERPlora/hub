"""``manage.py demo_expire <slug>``: end the demo ``<slug>`` now and purge it at once (plan 2026-10-17, §1.7).

Support's tool (a demo to close by hand) and the e2e's clock (a demo that ended, without waiting an hour), in every
environment. All through operations: ``base.demo.expire`` (its host answers 410 from now on), one pass of the reaper
(``reap_demos``, which purges it with ``base.demo.purge``), then ``base.demo.get`` to say how it was left.

While the platform is frozen for a database upgrade (``control.freeze.set``; hub#930) the demo ends all the same but its
database is left where it is (a ``DROP DATABASE`` would never reach the upgrade's copy): the worker's reaper drops it on
its first tick after the freeze is lifted, and the command says so.
"""

from django.core.management.base import BaseCommand, CommandError
from live.context import system_context
from live.errors import NotFound

from base.queries import demo_get
from base.registry import REGISTRY_SCOPE
from base.schemas import DemoSlugIn
from base.services import demo_expire, reap_demos
from base.tenancy.context import use_control
from control.queries import active_freeze


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
        if not frozen:
            reap_demos()
        status = demo_get(ctx, DemoSlugIn(slug=slug)).status
        if frozen:
            self.stdout.write(f"{slug}: {status} (frozen: its database is dropped once the freeze is lifted)")
            return
        self.stdout.write(f"{slug}: {status}")
