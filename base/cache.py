"""The caches without Valkey, refusing what the Valkey cluster of AWS refuses: one call on several keys whose hash
slots differ.

In AWS the cache is ElastiCache Serverless, a Valkey cluster: ``get_many`` (``MGET``), ``delete_many`` (one ``DEL`` of
every key) and ``set_many`` (``MSET`` inside a ``MULTI``) are answered ``CROSSSLOT`` when their keys hash to different
slots, and Django's ``RedisCache`` raises redis-py's ``ClusterCrossSlotError``. That went unseen for weeks: the PIN
limit read its count and the end of its window in one ``get_many``, was refused on every call and stepped aside, so the
PIN pad took nine wrong PINs in a row (hub#440). Without Valkey the cache refuses the same calls with the same error,
so what breaks in AWS breaks here first: local development keeps it on the machine's disk with
:class:`ClusterFileBasedCache`, one folder per control database (:func:`local_location`), so the web server and the
worker share it as they share Valkey in AWS (what one forgets, the other no longer reads: hub#707); the tests keep it
in the process's memory with :class:`ClusterLocMemCache`.

Keys that go in one call share a hash tag: a cluster computes the slot from what is between the key's first ``{`` and
the next ``}`` (``base.files:{<hub>}:folders`` and ``base.files:{<hub>}:bytes``), of the key as stored, with the
cache's prefix and version in front. A call on one key, or on keys of one tag, is always accepted.
"""

import pickle
import tempfile
import time
import zlib
from collections.abc import Iterable
from pathlib import Path

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.filebased import FileBasedCache
from django.core.cache.backends.locmem import LocMemCache
from redis.crc import key_slot
from redis.exceptions import ClusterCrossSlotError


def local_location(database: str) -> str:
    """The folder of the cache without Valkey of the processes on control database ``database``: two stacks on one
    machine (two checkouts, two e2e runs) have their own businesses under the same slugs."""
    return str(Path(tempfile.gettempdir(), "erplora-hub-cache", database))


class ClusterSlots:
    """A cache whose calls on several keys of different hash slots raise ``ClusterCrossSlotError``, with the message a
    Valkey cluster answers, before touching anything."""

    def _one_slot(self, keys: Iterable[str], version: int | None) -> None:
        slots = {key_slot(self.make_and_validate_key(key, version=version).encode()) for key in keys}
        if len(slots) > 1:
            raise ClusterCrossSlotError("Keys in request don't hash to the same slot")

    def get_many(self, keys, version=None):
        keys = list(keys)
        self._one_slot(keys, version)
        return super().get_many(keys, version=version)

    def set_many(self, data, timeout=DEFAULT_TIMEOUT, version=None):
        self._one_slot(data, version)
        return super().set_many(data, timeout=timeout, version=version)

    def delete_many(self, keys, version=None):
        keys = list(keys)
        self._one_slot(keys, version)
        return super().delete_many(keys, version=version)


class ClusterLocMemCache(ClusterSlots, LocMemCache):
    """Django's ``LocMemCache``, the process's memory, refusing what a Valkey cluster refuses."""


class ClusterFileBasedCache(ClusterSlots, FileBasedCache):
    """Django's ``FileBasedCache``, shared by every process of the machine that opens its folder, refusing what a
    Valkey cluster refuses."""

    def incr(self, key, delta=1, version=None):
        """Valkey's ``INCR``: the key keeps its expiry. Django's would write it again with the default timeout, so a
        window of the attempt limits (``base.throttle``) would last that long. Not atomic between processes."""
        try:
            with open(self._key_to_file(key, version), "rb") as file:
                expiry = pickle.load(file)
                value = pickle.loads(zlib.decompress(file.read()))
        except FileNotFoundError:
            raise ValueError(f"Key '{key}' not found") from None
        left = None if expiry is None else expiry - time.time()
        if left is not None and left <= 0:
            raise ValueError(f"Key '{key}' not found")
        self.set(key, value + delta, timeout=left, version=version)
        return value + delta
