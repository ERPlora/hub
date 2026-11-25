"""The files of a hub that is gone: its whole prefix deleted, and the hubs the store still holds."""

import itertools
import re
import uuid

from django.core.files.storage import Storage
from live.errors import OperationError
from storages.backends.s3 import S3Storage

from base.files.store import NOT_A_FOLDER, STORE_ERRORS, _prune, _store, scan
from base.storage import hub_prefix

#: The keys one ``DeleteObjects`` takes at most.
S3_DELETE_BATCH = 1000
#: A top folder of the store that is a hub's prefix, as :func:`base.storage.hub_prefix` names it: its id's 32 hex.
HUB_PREFIX = re.compile(r"hub-([0-9a-f]{32})")


class HubFilesNotDeleted(Exception):
    """Part of a hub's prefix may still be in the store: who purges the hub notes it and tries again, never done."""


def delete_hub_files(store: Storage, hub: uuid.UUID) -> None:
    """Delete everything under ``hub``'s prefix, its Files and what its apps keep beside them, and no key of any other
    hub: only its database's end calls this (``base.services.demos.purge_demo_data``, ``base.tenancy.offboarding``), the
    hub never comes back. Safe to run again: nothing left is no failure.

    In a versioned bucket a key leaves a delete marker, and its old version goes with the bucket's lifecycle rule."""
    prefix = hub_prefix(hub)
    try:
        keys = [f"{prefix}/{item.key}" for item in scan(store, prefix)]
        if isinstance(store, S3Storage):
            _delete_s3_keys(store, prefix, keys)
        else:
            for key in keys:
                store.delete(key)
            _prune(store, prefix)
    except (*STORE_ERRORS, OperationError) as error:
        cause = error.__cause__ or error
        raise HubFilesNotDeleted(f"{prefix}: {type(cause).__name__}: {cause}") from error


def hubs_in_store(store: Storage) -> list[uuid.UUID]:
    """The hubs whose prefix holds anything in the store, by id: its top folders named as a hub's prefix
    (:data:`HUB_PREFIX`). Anything else at the top, as ``shared/`` (the blueprints' catalog) or ``_inventory/`` (S3's
    inventory), is no hub's and is left out; a disk where nothing was kept yet holds none. What the store could not do
    is 503 ``base.file_store_unavailable``, never «no hub»."""
    with _store():
        try:
            folders, _names = store.listdir("")
        except NOT_A_FOLDER:
            return []
    return sorted(uuid.UUID(found[1]) for folder in folders if (found := HUB_PREFIX.fullmatch(folder)))


def _delete_s3_keys(store: S3Storage, prefix: str, keys: list[str]) -> None:
    """``DeleteObjects`` answers 200 and lists the keys it did not delete: boto3 raises nothing for those. The row the
    failure ends on keeps no file's name of the business, only how many and why."""
    s3 = store.connection.meta.client
    for batch in itertools.batched(keys, S3_DELETE_BATCH):
        answer = s3.delete_objects(
            Bucket=store.bucket_name, Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True}
        )
        if refused := answer.get("Errors"):
            raise HubFilesNotDeleted(f"{prefix}: {len(refused)} of {len(batch)} keys stayed: {refused[0]['Code']}")
