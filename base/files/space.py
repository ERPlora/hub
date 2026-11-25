"""The space a hub's prefix takes in the store, and the plan's limit on it."""

import uuid

from django.core.files.storage import Storage
from django.utils.translation import gettext
from live.errors import Conflict
from storages.backends.s3 import S3Storage

from base.files.index import _index
from base.files.names import _base
from base.files.store import NOT_A_FOLDER, _store, scan
from base.storage import hub_prefix

GIB = 1024**3


def used_bytes(store: Storage, hub: uuid.UUID) -> int:
    """What the hub's whole prefix takes in the store: its files (the kept index) and its apps' (counted now)."""
    return _index(store, hub).files_bytes + _apps_bytes(store, hub)


def _apps_bytes(store: Storage, hub: uuid.UUID) -> int:
    """What the hub's apps keep beside its files (the website's images): counted at every call, never kept, because
    the apps write there without Files knowing. It is small: the apps' own folders, never the business's files."""
    prefix = hub_prefix(hub)
    with _store():
        if isinstance(store, S3Storage):
            pages = store.connection.meta.client.get_paginator("list_objects_v2").paginate(
                Bucket=store.bucket_name, Prefix=f"{prefix}/", Delimiter="/"
            )
            size, folders = 0, []
            for page in pages:
                size += sum(int(item["Size"]) for item in page.get("Contents", []))
                folders += [entry["Prefix"].rstrip("/") for entry in page.get("CommonPrefixes", [])]
        else:
            try:
                below, names = store.listdir(prefix)
            except NOT_A_FOLDER:
                return 0
            size = sum(store.size(f"{prefix}/{name}") for name in names)
            folders = [f"{prefix}/{folder}" for folder in below]
    return size + sum(item.size for folder in folders if folder != _base(hub) for item in scan(store, folder))


def space_limit(state: object) -> int | None:
    """The space for files the plan in the SaaS's photo includes (``plan.max_storage_bytes``); ``None``: no limit
    (no photo, no plan, or no positive whole number of bytes)."""
    plan = state.get("plan") if isinstance(state, dict) else None
    limit = plan.get("max_storage_bytes") if isinstance(plan, dict) else None
    return limit if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0 else None


def refuse_past_the_space(store: Storage, hub: uuid.UUID, size: int, *, limit_bytes: int | None) -> None:
    """409 ``base.file_no_space`` when ``size`` more bytes go past ``limit_bytes`` (the plan's space; ``None``: no
    limit) with what ``hub``'s prefix already takes: its files and what its apps keep. The one check of the plan's
    space: Files and every app that keeps a file in the hub file store refuse through it, with the same sentence."""
    if limit_bytes is not None and used_bytes(store, hub) + size > limit_bytes:
        raise Conflict(
            gettext("There is no space left for that file: your plan includes %(space)s.")
            % {"space": human_space(limit_bytes)},
            code="base.file_no_space",
        )


def human_space(size: int) -> str:
    """A plan's space as the person reads it: «1 GB», «500 MB»."""
    if size >= GIB and size % GIB == 0:
        return f"{size // GIB} GB"
    return f"{max(1, round(size / (1024 * 1024)))} MB"
