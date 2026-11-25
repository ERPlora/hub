"""Uploading a file and making a new folder, never over what is there."""

import os
import posixpath
import uuid

from botocore.exceptions import ClientError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.translation import gettext
from live.errors import Conflict, InvalidPayload
from storages.backends.s3 import S3Storage
from storages.utils import clean_name as s3_clean_name

from base.files.index import _changed
from base.files.names import MARKER, MAX_NAME_BYTES, _join, _key, _refuse_program, clean_name, clean_path, served
from base.files.space import refuse_past_the_space
from base.files.store import _kind, _refuse_taken, _require_folder, _store

#: The heaviest file the manager takes (the old hub's ceiling to show one).
MAX_FILE_BYTES = 25 * 1024 * 1024
#: The longest name of a new folder, in characters (the old hub's dialog).
MAX_FOLDER_NAME = 100
#: How many times an upload takes the next free name because another upload of that name wrote it first.
MAX_NAME_RACES = 10


def upload(  # noqa: PLR0913
    store: Storage, hub: uuid.UUID, folder: str, name: str, content: bytes, *, limit_bytes: int | None = None
) -> dict:
    """Keep ``content`` as ``name`` in ``folder``, numbered («name (1).ext») when the name is taken."""
    folder = clean_path(folder)
    name = clean_name(name)
    _refuse_program(name)
    if len(content) > MAX_FILE_BYTES:
        message = gettext("That file weighs more than %(mb)s MB, the most Files takes.") % {
            "mb": MAX_FILE_BYTES // (1024 * 1024)
        }
        raise InvalidPayload(message, code="base.file_too_large", fields={"content_base64": message})
    _require_folder(store, hub, folder)
    refuse_past_the_space(store, hub, len(content), limit_bytes=limit_bytes)
    # The free name is worked out, then written only if nobody wrote it meanwhile (another upload of the same name at
    # the same moment): if somebody did, the next free name, never over the other's file.
    for _attempt in range(MAX_NAME_RACES):
        final = _free_name(store, hub, folder, name)
        path = _join(folder, final)
        if _create(store, _key(hub, path), content):
            _changed(hub, uploaded=len(content))
            return {"path": path, "name": final, "size": len(content)}
    raise Conflict(gettext("There is already a file or folder with that name here."), code="base.file_exists")


def _create(store: Storage, key: str, content: bytes) -> bool:
    """Write ``content`` as ``key`` only if no key of that name is there; ``False`` if one is (never written over).

    On S3 the write itself is conditional (``If-None-Match: *``: 412 when the key exists, 409 when another conditional
    write of it is under way); on disk the file is opened to be created (``O_EXCL``). Any other store (memory, in the
    tests) checks and writes."""
    with _store():
        if isinstance(store, S3Storage):
            content_type, _preview = served(posixpath.basename(key))
            try:
                store.connection.meta.client.put_object(
                    Bucket=store.bucket_name,
                    Key=store._normalize_name(s3_clean_name(key)),
                    Body=content,
                    ContentType=content_type,
                    IfNoneMatch="*",
                )
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in ("PreconditionFailed", "ConditionalRequestConflict"):
                    return False
                raise
            return True
        if isinstance(store, FileSystemStorage):
            path = store.path(key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            try:
                handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666)
            except FileExistsError:
                return False
            with os.fdopen(handle, "wb") as written:
                written.write(content)
            if store.file_permissions_mode is not None:
                os.chmod(path, store.file_permissions_mode)
            return True
        if store.exists(key):
            return False
        store.save(key, ContentFile(content))
        return True


def _free_name(store: Storage, hub: uuid.UUID, folder: str, name: str) -> str:
    """``name``, or the first «stem (n).ext» nobody has in ``folder``."""
    stem, dot, extension = name.rpartition(".")
    if not (dot and stem):
        stem, extension = name, ""
    suffix = f".{extension}" if extension else ""
    candidate, number = name, 0
    while _kind(store, hub, _join(folder, candidate)) is not None:
        number += 1
        candidate = f"{stem} ({number}){suffix}"
        if len(candidate.encode()) > MAX_NAME_BYTES:
            raise Conflict(gettext("There is already a file or folder with that name here."), code="base.file_exists")
    return candidate


def create_folder(store: Storage, hub: uuid.UUID, parent: str, name: str) -> dict:
    """A new, empty folder ``name`` in ``parent``; never over a file or folder that is there."""
    parent = clean_path(parent)
    name = clean_name(name, max_chars=MAX_FOLDER_NAME)
    _require_folder(store, hub, parent)
    path = _join(parent, name)
    _refuse_taken(store, hub, path)
    try:
        with _store():
            store.save(_key(hub, f"{path}/{MARKER}"), ContentFile(b""))
    finally:
        _changed(hub)
    return {"path": path, "name": name}
