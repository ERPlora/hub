"""A hub's index: its folders and what its files take, kept in the cache between operations."""

import logging
import uuid
from dataclasses import dataclass

from django.core.cache import cache
from django.core.files.storage import Storage

from base.files.names import MARKER, _base, _is_name
from base.files.store import scan

logger = logging.getLogger("base.files")  # the name Files has always logged under

#: How long a hub's index (its folders and what its files take) is kept: every write of Files updates or forgets it,
#: so this only bounds what an update lost while the cache was away could leave behind.
INDEX_SECONDS = 600


@dataclass(frozen=True)
class Index:
    """The folders of a hub's files (their paths under the root) and what the files take, from one walk of the root."""

    folders: frozenset[str]
    files_bytes: int


def _index_keys(hub: uuid.UUID) -> tuple[str, str, str]:
    """The index's keys, read, kept and forgotten together: the hub is their hash tag (``{<hex>}``), one slot of the
    Valkey cluster for the three, which refuses a call on keys of different slots (``base/cache.py``)."""
    tag = f"base.files:{{{hub.hex}}}"
    return f"{tag}:folders", f"{tag}:bytes", f"{tag}:generation"


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
