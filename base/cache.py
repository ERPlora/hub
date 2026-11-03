"""This process's memory as the cache, refusing what the Valkey cluster of AWS refuses: one call on several keys
whose hash slots differ.

In AWS the cache is ElastiCache Serverless, a Valkey cluster: ``get_many`` (``MGET``), ``delete_many`` (one ``DEL`` of
every key) and ``set_many`` (``MSET`` inside a ``MULTI``) are answered ``CROSSSLOT`` when their keys hash to different
slots, and Django's ``RedisCache`` raises redis-py's ``ClusterCrossSlotError``. That went unseen for weeks: the PIN
limit read its count and the end of its window in one ``get_many``, was refused on every call and stepped aside, so the
PIN pad took nine wrong PINs in a row (hub#440). Local development and the tests keep the cache in memory with
:class:`ClusterLocMemCache`, which refuses the same calls with the same error: what breaks in AWS breaks here first.

Keys that go in one call share a hash tag: a cluster computes the slot from what is between the key's first ``{`` and
the next ``}`` (``base.files:{<hub>}:folders`` and ``base.files:{<hub>}:bytes``), of the key as stored, with the
cache's prefix and version in front. A call on one key, or on keys of one tag, is always accepted.
"""

from collections.abc import Iterable

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.locmem import LocMemCache
from redis.crc import key_slot
from redis.exceptions import ClusterCrossSlotError


class ClusterLocMemCache(LocMemCache):
    """Django's ``LocMemCache`` whose calls on several keys of different hash slots raise ``ClusterCrossSlotError``,
    with the message a Valkey cluster answers, before touching anything."""

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
