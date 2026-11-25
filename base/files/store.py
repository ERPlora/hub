"""Reaching the hub file store: what it could not do, its keys under a prefix, and what a path is there."""

import datetime as dt
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from botocore.exceptions import BotoCoreError, ClientError
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.translation import gettext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError
from storages.backends.s3 import S3Storage

from base.files.names import MARKER, _key

#: What a store raises when it cannot do what was asked (the disk, S3 or its client).
STORE_ERRORS = (OSError, BotoCoreError, ClientError)
#: What listing a name that is no folder raises: missing, or a file (on disk; in memory, ``FileExistsError``).
NOT_A_FOLDER = (FileNotFoundError, NotADirectoryError, FileExistsError)


@dataclass(frozen=True)
class Stored:
    """A key of the store under a prefix: its rest after the prefix, its size and when it was last written."""

    key: str
    size: int
    modified: dt.datetime | None


@contextmanager
def _store() -> Iterator[None]:
    """What the store could not do, as 503 ``base.file_store_unavailable``: never taken for «empty» or «missing»."""
    try:
        yield
    except STORE_ERRORS as exc:
        raise OperationError(
            gettext("The file store did not answer. Try again in a moment."),
            code="base.file_store_unavailable",
            status=503,
        ) from exc


def scan(store: Storage, prefix: str) -> list[Stored]:
    """Every key under ``prefix`` (a folder of the store, without its ``/``), with its size and time.

    On S3, ``ListObjectsV2`` pages of a thousand keys, never a request per file; elsewhere, the folders walked."""
    with _store():
        if isinstance(store, S3Storage):
            pages = store.connection.meta.client.get_paginator("list_objects_v2").paginate(
                Bucket=store.bucket_name, Prefix=f"{prefix}/"
            )
            start = len(prefix) + 1
            return [
                Stored(item["Key"][start:], int(item["Size"]), item.get("LastModified"))
                for page in pages
                for item in page.get("Contents", [])
            ]
        return list(_walk(store, prefix, ""))


def _walk(store: Storage, prefix: str, below: str) -> Iterator[Stored]:
    here = f"{prefix}/{below}" if below else prefix
    try:
        folders, names = store.listdir(here)
    except NOT_A_FOLDER:
        return
    for name in names:
        key = f"{here}/{name}"
        yield Stored(f"{below}/{name}" if below else name, store.size(key), _modified(store, key))
    for folder in folders:
        yield from _walk(store, prefix, f"{below}/{folder}" if below else folder)


def _modified(store: Storage, key: str) -> dt.datetime | None:
    try:
        return store.get_modified_time(key)
    except NotImplementedError:  # Django's Storage raises it for a backend that keeps no times: none to show
        return None


def _kind(store: Storage, hub: uuid.UUID, path: str) -> Literal["file", "folder"] | None:
    """Whether ``path`` is a file, a folder (with something in it, or an empty folder on disk) or nothing."""
    key = _key(hub, path)
    with _store():
        try:
            folders, names = store.listdir(key)
            listed = True
        except NOT_A_FOLDER:
            folders, names, listed = [], [], False
        if folders or names:
            return "folder"
        if not store.exists(key):
            return None
    # On S3 every name lists (as nothing); on disk and in memory only a folder does.
    return "folder" if listed and not isinstance(store, S3Storage) else "file"


def _folder_exists(store: Storage, hub: uuid.UUID, folder: str) -> bool:
    return not folder or _kind(store, hub, folder) == "folder"


def _require_folder(store: Storage, hub: uuid.UUID, folder: str) -> None:
    if not _folder_exists(store, hub, folder):
        raise NotFound(gettext("That folder no longer exists. Refresh the list."), code="base.file_folder_missing")


def _require(store: Storage, hub: uuid.UUID, path: str) -> Literal["file", "folder"]:
    if not path:
        raise InvalidPayload(gettext("That file or folder is not in this business's files."), code="base.file_invalid_path")
    kind = _kind(store, hub, path)
    if kind is None:
        raise NotFound(gettext("That file or folder no longer exists. Refresh the list."), code="base.file_missing")
    return kind


def _refuse_taken(store: Storage, hub: uuid.UUID, path: str) -> None:
    if _kind(store, hub, path) is not None:
        raise Conflict(gettext("There is already a file or folder with that name here."), code="base.file_exists")


def _keep_folder(store: Storage, hub: uuid.UUID, folder: str) -> None:
    """``folder`` stays once what was in it left: an object store only has the folders its keys name."""
    if folder:
        with _store():
            marker = _key(hub, f"{folder}/{MARKER}")
            if not store.exists(marker):
                store.save(marker, ContentFile(b""))


def _prune(store: Storage, key: str) -> None:
    """The folders left empty under ``key``, and ``key`` itself (on disk and in memory; S3 has none)."""
    if isinstance(store, S3Storage):
        return
    try:
        folders, _names = store.listdir(key)
    except NOT_A_FOLDER:
        return
    for folder in folders:
        _prune(store, f"{key}/{folder}")
    store.delete(key)
