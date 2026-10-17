"""``manage.py demo_expire <slug>``: end the demo ``<slug>`` now and purge it at once (plan 2026-10-17, §1.7).

Support's tool (a demo to close by hand) and the e2e's clock (a demo that ended, without waiting an hour), in every
environment. All through operations: ``base.demo.expire`` (its host answers 410 from now on), one pass of the reaper
(``reap_demos``, which purges it with ``base.demo.purge``), then ``base.demo.get`` to say how it was left.
"""

from django.core.management.base import BaseCommand, CommandError
from live.context import system_context
from live.errors import NotFound

from base.queries import demo_get
from base.registry import REGISTRY_SCOPE
from base.schemas import DemoSlugIn
from base.services import demo_expire, reap_demos


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
        reap_demos()
        status = demo_get(ctx, DemoSlugIn(slug=slug)).status
        self.stdout.write(f"{slug}: {status}")
