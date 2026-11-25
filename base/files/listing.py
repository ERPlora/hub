"""The listing of a folder: the tree of folders, its crumbs, and the files right in it."""

import posixpath
import uuid

from django.core.files.storage import Storage
from django.utils.translation import gettext
from live.errors import NotFound
from storages.backends.s3 import S3Storage

from base.files.index import _index
from base.files.names import MARKER, _is_name, _key, clean_path, served
from base.files.space import _apps_bytes
from base.files.store import NOT_A_FOLDER, Stored, _modified, _store


def listing(store: Storage, hub: uuid.UUID, folder: str) -> dict:
    """The tree of folders (the kept index), the files of ``folder`` read alone, and the space the hub's whole prefix
    takes: what its files take (kept) and what its apps keep (counted now)."""
    folder = clean_path(folder)
    index = _index(store, hub)
    if folder and folder not in index.folders:
        raise NotFound(gettext("That folder no longer exists. Refresh the list."), code="base.file_folder_missing")
    here = []
    for item in _folder_files(store, hub, folder):
        if item.key == MARKER or not _is_name(item.key):
            continue  # a key the manager would not have written (another tool's): never shown
        content_type, preview = served(item.key)
        here.append(
            {
                "path": f"{folder}/{item.key}" if folder else item.key,
                "name": item.key,
                "size": item.size,
                "modified": item.modified,
                "content_type": content_type,
                "preview": preview,
            }
        )
    return {
        "folder": folder,
        "crumbs": _crumbs(folder),
        "folders": _tree(set(index.folders), ""),
        "files": sorted(here, key=lambda item: _order(item["name"])),
        "used_bytes": index.files_bytes + _apps_bytes(store, hub),
    }


def _folder_files(store: Storage, hub: uuid.UUID, folder: str) -> list[Stored]:
    """The keys right in ``folder``, not in its sub-folders, read alone (on S3, ``ListObjectsV2`` with ``Delimiter``)."""
    key = _key(hub, folder)
    with _store():
        if isinstance(store, S3Storage):
            pages = store.connection.meta.client.get_paginator("list_objects_v2").paginate(
                Bucket=store.bucket_name, Prefix=f"{key}/", Delimiter="/"
            )
            start = len(key) + 1
            return [
                Stored(item["Key"][start:], int(item["Size"]), item.get("LastModified"))
                for page in pages
                for item in page.get("Contents", [])
            ]
        try:
            _folders, names = store.listdir(key)
        except NOT_A_FOLDER:
            return []
        return [Stored(name, store.size(f"{key}/{name}"), _modified(store, f"{key}/{name}")) for name in names]


def _order(name: str) -> tuple[str, str]:
    return name.casefold(), name


def _crumbs(folder: str) -> list[dict]:
    parts = folder.split("/") if folder else []
    return [{"path": "/".join(parts[: index + 1]), "name": part} for index, part in enumerate(parts)]


def _tree(folders: set[str], parent: str) -> list[dict]:
    children = sorted(
        (path for path in folders if posixpath.dirname(path) == parent), key=lambda path: _order(posixpath.basename(path))
    )
    return [{"path": path, "name": posixpath.basename(path), "children": _tree(folders, path)} for path in children]
