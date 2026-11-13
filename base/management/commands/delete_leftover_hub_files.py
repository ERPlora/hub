"""``manage.py delete_leftover_hub_files``: the files left in the store by hubs purged before a purge deleted a hub's
files, deleted once.

A purge deletes the hub's files after its database (``base.files.delete_hub_files``, BASE-F109 and PUBLIC-F34), but a
row already ``purged`` never goes through the purge again, so whatever it kept from before stayed. This finds each
top folder of the hub file store named as a hub's prefix (``hub-<hex>``) whose hub is gone for good: ``purged``, or with
no row in the registry any more (a demo's tombstone, forgotten after its days; ``base.services.gone_hubs``). Every other
status keeps its files, anything at the top that is no hub's prefix (``shared/``, ``_inventory/``) is never looked
into, and no hub's database is opened. A prefix that holds no key is left out: in the versioned bucket, one already
deleted may still list for its delete markers.

By default it only lists them, each with its keys and bytes, and deletes nothing; ``--delete`` deletes them, one prefix
at a time, each with ``base.files.delete_hub_files``. The store is listed before the registry is read: a hub's row exists
before its first file, so a hub made in between is never taken for gone. A store that cannot be listed deletes
nothing; a prefix that fails is said and the others go on, and the run ends in an error naming it (running it again
finishes it). In the versioned bucket each key leaves a delete marker, and its old version goes with the bucket's
``noncurrent`` rule. Runs where the hubs' bucket is written: in AWS, a one-off task of the ``worker`` family.
"""

from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError
from live.errors import OperationError

from base import files, services
from base.storage import hub_prefix
from base.tenancy.context import use_control


class Command(BaseCommand):
    help = (
        "List the prefixes of the hub file store whose hub is purged or no longer in the registry (left by purges "
        "that did not yet delete a hub's files); --delete deletes them. Never a hub that is not gone, nor shared/."
    )

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Delete what is listed (by default, nothing is).")

    def handle(self, *args, delete=False, **options):
        store = storages["hub_files"]
        try:
            in_store = files.hubs_in_store(store)
            with use_control():
                gone = services.gone_hubs(in_store)
            # Only a prefix that still holds keys: in a versioned bucket a deleted one keeps its delete markers.
            left = {hub_id: kept for hub_id in gone if (kept := files.scan(store, hub_prefix(hub_id)))}
        except OperationError as error:
            raise CommandError(f"{error.code}: the file store did not answer, nothing was deleted.") from error
        self.stdout.write(f"Hubs with files in the store: {len(in_store)}; gone for good: {len(left)}")
        for hub_id, kept in left.items():
            self.stdout.write(
                f"- {hub_prefix(hub_id)}: {self._why(gone[hub_id])}, {len(kept)} keys, "
                f"{sum(item.size for item in kept)} bytes"
            )
        if not delete:
            self.stdout.write("Dry run: nothing was deleted (--delete deletes what is listed).")
            return
        failed = []
        for hub_id in left:
            try:
                files.delete_hub_files(store, hub_id)
            except files.HubFilesNotDeleted as error:
                failed.append(str(error))
                self.stdout.write(f"{hub_prefix(hub_id)}: not deleted: {error}")
                continue
            self.stdout.write(f"{hub_prefix(hub_id)}: deleted")
        if failed:
            raise CommandError(
                f"{len(failed)} of {len(left)} prefixes stayed (run it again):\n" + "\n".join(f"- {f}" for f in failed)
            )

    @staticmethod
    def _why(hub) -> str:
        if hub is None:
            return "no row in the registry"
        kind = "demo" if hub.is_demo else "business"
        when = hub.purged_at.date().isoformat() if hub.purged_at else "an unknown day"
        return f"{kind} {hub.slug}, purged on {when}"
