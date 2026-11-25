"""Reading a file: what it is and its bytes, for the person who asked."""

import posixpath
import uuid
from urllib.parse import quote

from django.core.files.base import File
from django.core.files.storage import Storage
from django.http import FileResponse
from django.utils.translation import gettext
from live.errors import NotFound

from base.files.names import _key, clean_path, served
from base.files.store import _require, _store
from base.media import FILE_CSP


def describe(store: Storage, hub: uuid.UUID, path: str) -> dict:
    """The file at ``path``: its name, size, the type it is served with and how the screen shows it."""
    path = clean_path(path)
    if _require(store, hub, path) != "file":
        raise NotFound(gettext("That file or folder no longer exists. Refresh the list."), code="base.file_missing")
    name = posixpath.basename(path)
    content_type, preview = served(name)
    with _store():
        size = store.size(_key(hub, path))
    return {"path": path, "name": name, "size": size, "content_type": content_type, "preview": preview}


def open_file(store: Storage, hub: uuid.UUID, path: str) -> File:
    """The bytes of the file at ``path`` (described first by :func:`describe`), to stream."""
    with _store():
        return store.open(_key(hub, clean_path(path)), "rb")


def file_response(store: Storage, hub: uuid.UUID, described: dict, *, inline: bool) -> FileResponse:
    """The file ``described`` (by ``base.file.read``) for the person who asked: never cached, sandboxed if opened on
    its own, and an attachment unless it is a type that is safe to show and the page asked to show it."""
    content_type = described["content_type"]
    response = FileResponse(
        open_file(store, hub, described["path"]),
        content_type="text/plain; charset=utf-8" if content_type == "text/plain" else content_type,
    )
    shown = inline and described["preview"] != ""
    response["Content-Disposition"] = f"{'inline' if shown else 'attachment'}; filename*=UTF-8''{quote(described['name'], safe='')}"
    response["Cache-Control"] = "private, no-store"
    response._csp_config = FILE_CSP
    return response
