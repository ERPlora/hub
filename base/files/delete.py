"""Deleting a file, or a folder with everything in it."""

import posixpath
import uuid

from django.core.files.storage import Storage

from base.files.index import _changed
from base.files.names import _key, clean_path
from base.files.store import _keep_folder, _prune, _require, _store, scan


def delete(store: Storage, hub: uuid.UUID, path: str) -> dict:
    """Delete the file at ``path``, or the folder and everything in it; there is no bin."""
    path = clean_path(path)
    kind = _require(store, hub, path)
    try:
        with _store():
            if kind == "file":
                store.delete(_key(hub, path))
            else:
                for item in scan(store, _key(hub, path)):
                    store.delete(_key(hub, f"{path}/{item.key}"))
                _prune(store, _key(hub, path))
        _keep_folder(store, hub, posixpath.dirname(path))
    finally:
        _changed(hub)
    return {"path": path, "folder": kind == "folder"}
