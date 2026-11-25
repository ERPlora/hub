"""Renaming and moving a file or a folder: every key copied, then the old ones deleted."""

import logging
import posixpath
import uuid

from django.core.files.storage import Storage
from django.utils.translation import gettext
from live.errors import Conflict, OperationError

from base.files.index import _changed
from base.files.names import _join, _key, _refuse_program, clean_name, clean_path
from base.files.store import STORE_ERRORS, _keep_folder, _prune, _refuse_taken, _require, _require_folder, _store, scan

logger = logging.getLogger("base.files")  # the name Files has always logged under


def rename(store: Storage, hub: uuid.UUID, path: str, name: str) -> dict:
    """Give the file or folder at ``path`` the name ``name``, in the same folder (a name, never a path)."""
    path = clean_path(path)
    kind = _require(store, hub, path)
    name = clean_name(name)
    if kind == "file":
        _refuse_program(name)
    target = _join(posixpath.dirname(path), name)
    if target != path:
        _refuse_taken(store, hub, target)
        _relocate(store, hub, path, target, kind)
    return {"path": target, "name": name}


def move(store: Storage, hub: uuid.UUID, path: str, to: str) -> dict:
    """Put the file or folder at ``path`` into the folder ``to`` (``""``: the root), never over another."""
    path = clean_path(path)
    to = clean_path(to)
    kind = _require(store, hub, path)
    if kind == "folder" and (to == path or to.startswith(f"{path}/")):
        raise Conflict(gettext("A folder can't be moved inside itself."), code="base.file_move_into_itself")
    if to == posixpath.dirname(path):
        raise Conflict(gettext("It is already in that folder."), code="base.file_already_there")
    _require_folder(store, hub, to)
    name = posixpath.basename(path)
    target = _join(to, name)
    _refuse_taken(store, hub, target)
    _relocate(store, hub, path, target, kind)
    return {"path": target, "name": name}


def _relocate(store: Storage, hub: uuid.UUID, source: str, target: str, kind: str) -> None:
    """Copy every key of ``source`` to ``target``, then delete the old ones: an object store has no rename. If a copy
    fails, the copies made are deleted and nothing moved. Either way the hub's index is forgotten."""
    try:
        _copy_and_delete(store, hub, source, target, kind)
    finally:
        _changed(hub)


def _copy_and_delete(store: Storage, hub: uuid.UUID, source: str, target: str, kind: str) -> None:
    if kind == "file":
        pairs = [(source, target)]
    else:
        pairs = [(f"{source}/{item.key}", f"{target}/{item.key}") for item in scan(store, _key(hub, source))]
    copied: list[str] = []
    try:
        with _store():
            for old, new in pairs:
                with store.open(_key(hub, old), "rb") as content:
                    store.save(_key(hub, new), content)
                copied.append(new)
    except OperationError:
        for new in copied:
            try:
                store.delete(_key(hub, new))
            except STORE_ERRORS:
                # The source is untouched and the error is raised; this copy stays behind, said in the log.
                logger.warning("files: the copy %s of a failed move could not be deleted", _key(hub, new), exc_info=True)
        raise
    with _store():
        for old, _new in pairs:
            store.delete(_key(hub, old))
        if kind == "folder":
            _prune(store, _key(hub, source))
    _keep_folder(store, hub, posixpath.dirname(source))
