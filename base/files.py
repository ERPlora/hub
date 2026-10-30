"""The business's files (APP-BASE-8; the old hub's Files, ``media.rs`` and the SaaS's S3 media manager, ADR-0047).

What the Files screen keeps lives in the hub file store (``storages["hub_files"]``, ``base.storage``: S3 in AWS, the
disk locally) under the hub's prefix, in a folder of its own: ``hub-<hex>/files/<path>``. The modules keep theirs
beside it (``website/img/``, ``avatars/``) and the manager never shows nor touches them; nothing of it is public
(``/p/media/`` serves only the folders the apps declare, ``base.media``): a file is read through ``base.file.read``, with the
session and the permission of who asks.

A *name* is one segment (no ``/``, ``\\``, control character, lone dot, or the folder marker) of 255 UTF-8 bytes at
most; a *path* is a chain of names, ``""`` being the root. Both are checked before the store sees them, so no key
ever leaves its hub's folder (an S3 key folds ``..``: saas#972). Object stores have no folders: an empty one is kept
by its marker (``<folder>/.keep``), and renaming or moving copies every key and then deletes the old ones. Writing
never overwrites in silence: an upload takes «name (1).ext» when «name.ext» is taken (Google Drive, Dropbox), and a
new folder, a rename or a move onto a taken name is refused. Programs (Gmail's blocked list) are never kept.

A listing reads the open folder alone (``Delimiter``); the tree of folders and what the files take come from the hub's
index, kept in the cache between operations (an upload adds its bytes, any other write forgets it), so a batch of
uploads and the listings after each walk the files once. What the apps keep is counted at every call: the space
stays exact for the plan's limit.

These functions take the store and the hub's id, and raise ``live`` errors in the language that is active: the
operations (``base.queries``, ``base.services``) give them the hub of the request and the plan's space.
"""

import datetime as dt
import logging
import os
import posixpath
import unicodedata
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from botocore.exceptions import BotoCoreError, ClientError
from django.core.cache import cache
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage, Storage
from django.http import FileResponse
from django.utils.translation import gettext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError
from storages.backends.s3 import S3Storage
from storages.utils import clean_name as s3_clean_name

from base.media import FILE_CSP
from base.storage import hub_prefix

logger = logging.getLogger(__name__)

#: The folder under a hub's prefix that the Files screen shows: its root.
ROOT = "files"
#: What keeps an empty folder in an object store; never listed, never a name.
MARKER = ".keep"
#: The heaviest file the manager takes (the old hub's ceiling to show one).
MAX_FILE_BYTES = 25 * 1024 * 1024
#: The longest name, in UTF-8 bytes (a file name on disk).
MAX_NAME_BYTES = 255
#: The longest name of a new folder, in characters (the old hub's dialog).
MAX_FOLDER_NAME = 100
#: How long a hub's index (its folders and what its files take) is kept: every write of Files updates or forgets it,
#: so this only bounds what an update lost while the cache was away could leave behind.
INDEX_SECONDS = 600
#: How many times an upload takes the next free name because another upload of that name wrote it first.
MAX_NAME_RACES = 10
#: The longest path under the root, in UTF-8 bytes: with ``hub-<hex>/files/`` (43), an S3 key's 1024 at most.
MAX_PATH_BYTES = 980
#: Programs a file manager does not keep: they run on whoever opens them (the extensions Gmail blocks).
BLOCKED_EXTENSIONS = frozenset(
    {
        "ade", "adp", "apk", "appx", "appxbundle", "bat", "cab", "chm", "cmd", "com", "cpl", "diagcab",
        "diagcfg", "diagpack", "dll", "dmg", "ex_", "exe", "hta", "img", "ins", "iso", "isp", "jar", "jnlp",
        "js", "jse", "lib", "lnk", "mde", "msc", "msi", "msix", "msixbundle", "msp", "mst", "nsh", "pif",
        "ps1", "scr", "sct", "shb", "sys", "vb", "vbe", "vbs", "vhd", "vxd", "wsc", "wsf", "wsh", "xll",
    }
)  # fmt: skip
#: What a store raises when it cannot do what was asked (the disk, S3 or its client).
STORE_ERRORS = (OSError, BotoCoreError, ClientError)
#: What listing a name that is no folder raises: missing, or a file (on disk; in memory, ``FileExistsError``).
NOT_A_FOLDER = (FileNotFoundError, NotADirectoryError, FileExistsError)

Preview = Literal["image", "pdf", "text", "table", "json", "audio", "video", ""]
#: The type a file is served with and how the screen shows it, by extension. Our own table, not ``mimetypes``: the
#: slim image of production has no ``/etc/mime.types``. Markup and scripts are served as their source, as plain text
#: (a browser never runs them, saas#968); an SVG may carry script and is never shown; what is not here is bytes.
SERVED: dict[str, tuple[str, Preview]] = {
    **{ext: (f"image/{kind}", "image") for ext, kind in (
        ("jpg", "jpeg"), ("jpeg", "jpeg"), ("png", "png"), ("gif", "gif"), ("webp", "webp"), ("bmp", "bmp"),
        ("avif", "avif"),
    )},
    "pdf": ("application/pdf", "pdf"),
    **{ext: ("text/plain", "text") for ext in (
        "txt", "log", "md", "markdown", "ini", "conf", "cfg", "yaml", "yml", "xml", "html", "htm", "xhtml", "css",
        "js", "mjs", "ts", "py", "sql", "sh",
    )},
    **{ext: ("text/plain", "table") for ext in ("csv", "tsv")},
    "json": ("text/plain", "json"),
    **{ext: (kind, "audio") for ext, kind in (
        ("mp3", "audio/mpeg"), ("wav", "audio/wav"), ("ogg", "audio/ogg"), ("oga", "audio/ogg"), ("m4a", "audio/mp4"),
        ("aac", "audio/aac"),
    )},
    **{ext: (kind, "video") for ext, kind in (
        ("mp4", "video/mp4"), ("m4v", "video/mp4"), ("webm", "video/webm"), ("ogv", "video/ogg"),
        ("mov", "video/quicktime"),
    )},
    **{ext: (kind, "") for ext, kind in (
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("xlsm", "application/vnd.ms-excel.sheet.macroEnabled.12"),
        ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("doc", "application/msword"), ("xls", "application/vnd.ms-excel"), ("ppt", "application/vnd.ms-powerpoint"),
        ("odt", "application/vnd.oasis.opendocument.text"), ("ods", "application/vnd.oasis.opendocument.spreadsheet"),
        ("odp", "application/vnd.oasis.opendocument.presentation"), ("rtf", "application/rtf"),
        ("zip", "application/zip"), ("heic", "image/heic"),
    )},
}  # fmt: skip
BYTES = "application/octet-stream"
GIB = 1024**3


@dataclass(frozen=True)
class Stored:
    """A key of the store under a prefix: its rest after the prefix, its size and when it was last written."""

    key: str
    size: int
    modified: dt.datetime | None


# ── Names and paths ──────────────────────────────────────────────────────────────────────────────────────────


def clean_name(name: str, *, max_chars: int | None = None) -> str:
    """``name`` trimmed and in one Unicode form (NFC), or 422 ``base.file_invalid_name``."""
    clean = unicodedata.normalize("NFC", (name or "").strip())
    if not _is_name(clean) or (max_chars is not None and len(clean) > max_chars):
        message = gettext("That name is not valid. Use a name without slashes or lone dots.")
        raise InvalidPayload(message, code="base.file_invalid_name", fields={"name": message})
    return clean


def clean_path(path: str) -> str:
    """``path`` (``""`` = the root) in NFC, or 422 ``base.file_invalid_path`` if it could leave the files."""
    clean = unicodedata.normalize("NFC", path or "")
    if clean and (len(clean.encode()) > MAX_PATH_BYTES or not all(_is_name(part) for part in clean.split("/"))):
        raise InvalidPayload(gettext("That file or folder is not in this business's files."), code="base.file_invalid_path")
    return clean


def _is_name(name: str) -> bool:
    return (
        bool(name)
        and name not in (".", "..")
        and name.casefold() != MARKER
        and "/" not in name
        and "\\" not in name
        and not any(unicodedata.category(char) == "Cc" for char in name)
        and len(name.encode()) <= MAX_NAME_BYTES
    )


def served(name: str) -> tuple[str, Preview]:
    """The type ``name`` is served with and how the screen shows it (``""``: it does not, it is downloaded)."""
    return SERVED.get(_extension(name), (BYTES, ""))


def _extension(name: str) -> str:
    stem, dot, extension = name.rpartition(".")
    return extension.lower() if dot and stem else ""


def _join(folder: str, name: str) -> str:
    joined = f"{folder}/{name}" if folder else name
    if len(joined.encode()) > MAX_PATH_BYTES:
        message = gettext("That name is too long for this folder.")
        raise InvalidPayload(message, code="base.file_invalid_name", fields={"name": message})
    return joined


def _base(hub: uuid.UUID) -> str:
    return f"{hub_prefix(hub)}/{ROOT}"


def _key(hub: uuid.UUID, path: str) -> str:
    return f"{_base(hub)}/{path}" if path else _base(hub)


# ── The store ────────────────────────────────────────────────────────────────────────────────────────────────


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


def _refuse_program(name: str) -> None:
    extension = _extension(name)
    if extension in BLOCKED_EXTENSIONS:
        message = gettext("Programs (.%(extension)s) can't be kept in Files: they could harm whoever opens them.") % {
            "extension": extension
        }
        raise InvalidPayload(message, code="base.file_type_refused", fields={"name": message})


# ── Listing (BASE-G82) ───────────────────────────────────────────────────────────────────────────────────────


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


def used_bytes(store: Storage, hub: uuid.UUID) -> int:
    """What the hub's whole prefix takes in the store: its files (the kept index) and its apps' (counted now)."""
    return _index(store, hub).files_bytes + _apps_bytes(store, hub)


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


# ── The index: a hub's folders and what its files take, kept between operations ──────────────────────────────


@dataclass(frozen=True)
class Index:
    """The folders of a hub's files (their paths under the root) and what the files take, from one walk of the root."""

    folders: frozenset[str]
    files_bytes: int


def _index_keys(hub: uuid.UUID) -> tuple[str, str, str]:
    return f"base.files:{hub.hex}:folders", f"base.files:{hub.hex}:bytes", f"base.files:{hub.hex}:generation"


def _cached(what: str, call, default):
    """``call()`` on the cache, or ``default`` when the cache does not answer: the store is then walked, which costs
    time and never a wrong listing (the cache is a shortcut, Valkey in AWS)."""
    try:
        return call()
    except Exception:  # whatever the cache backend raises when it is away: said in the log, the store answers
        logger.warning("files: the cache could not %s", what, exc_info=True)
        return default


def _index(store: Storage, hub: uuid.UUID) -> Index:
    """The kept index of ``hub``, or one walk of its files' root (kept for the next operations)."""
    folders_key, bytes_key, generation_key = _index_keys(hub)
    kept = _cached("read the index", lambda: cache.get_many([folders_key, bytes_key, generation_key]), {})
    if folders_key in kept and bytes_key in kept:
        return Index(frozenset(kept[folders_key]), int(kept[bytes_key]))
    generation = kept.get(generation_key, 0)
    folders: set[str] = set()
    size = 0
    for item in scan(store, _base(hub)):
        size += item.size
        parts = item.key.split("/")
        if all(_is_name(part) for part in parts[:-1]) and (parts[-1] == MARKER or _is_name(parts[-1])):
            folders.update("/".join(parts[:index]) for index in range(1, len(parts)))
    # Kept first, the generation read back after: a write of Files that came while walking or while keeping (each one
    # moves the generation before it touches the index) forgets what was kept, so never what the walk missed. Read
    # back before keeping, a write landing in between (one round trip of the cache) stayed out until the index expired.
    _cached(
        "keep the index",
        lambda: cache.set_many({folders_key: sorted(folders), bytes_key: size}, INDEX_SECONDS),
        None,
    )
    if _cached("read the generation", lambda: cache.get(generation_key, 0), None) != generation:
        _cached("forget the index", lambda: cache.delete_many([folders_key, bytes_key]), None)
    return Index(frozenset(folders), size)


def _changed(hub: uuid.UUID, *, uploaded: int | None = None) -> None:
    """After a write of Files: an upload adds its bytes to the kept index (its folder was there already); any other
    write forgets the index, walked again by the next operation. Both move the generation first."""
    folders_key, bytes_key, generation_key = _index_keys(hub)

    def move_generation() -> None:
        cache.add(generation_key, 0, None)
        cache.incr(generation_key)

    _cached("move the generation", move_generation, None)
    if uploaded is None:
        _cached("forget the index", lambda: cache.delete_many([folders_key, bytes_key]), None)
        return

    def count() -> bool:
        try:
            cache.incr(bytes_key, uploaded)
        except ValueError:  # Django's answer for a key that is not kept: nothing to add to, the next listing walks
            return False
        return True

    _cached("count the upload", count, False)


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


# ── Upload and new folder (BASE-G83) ─────────────────────────────────────────────────────────────────────────


def upload(
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
    if limit_bytes is not None and used_bytes(store, hub) + len(content) > limit_bytes:
        raise Conflict(
            gettext("There is no space left for that file: your plan includes %(space)s.")
            % {"space": human_space(limit_bytes)},
            code="base.file_no_space",
        )
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


# ── Read (BASE-G84) ──────────────────────────────────────────────────────────────────────────────────────────


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


# ── Rename and move (BASE-G85) ───────────────────────────────────────────────────────────────────────────────


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


# ── Delete (BASE-G86) ────────────────────────────────────────────────────────────────────────────────────────


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


def space_limit(state: object) -> int | None:
    """The space for files the plan in the SaaS's photo includes (``plan.max_storage_bytes``); ``None``: no limit
    (no photo, no plan, or no positive whole number of bytes)."""
    plan = state.get("plan") if isinstance(state, dict) else None
    limit = plan.get("max_storage_bytes") if isinstance(plan, dict) else None
    return limit if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0 else None


def human_space(size: int) -> str:
    """A plan's space as the person reads it: «1 GB», «500 MB»."""
    if size >= GIB and size % GIB == 0:
        return f"{size // GIB} GB"
    return f"{max(1, round(size / (1024 * 1024)))} MB"
