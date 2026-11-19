"""``base.cache``: the caches without Valkey, refusing what a Valkey cluster refuses.

In AWS the cache is a Valkey cluster (ElastiCache Serverless): a call on several keys (``get_many``'s ``MGET``,
``delete_many``'s ``DEL``, ``set_many``'s ``MULTI``) whose keys hash to different slots is answered ``CROSSSLOT``
(hub#440: the PIN limit read its count and the end of its window in one ``get_many``, was refused on every call and
stepped aside). Local development keeps the cache on the machine's disk (``ClusterFileBasedCache``) and the tests in the
process's memory (``ClusterLocMemCache``); both refuse the same calls with redis-py's own error, so what breaks in AWS
breaks here first.
"""

import time

import pytest
from django.core.cache.backends.base import BaseCache
from redis.crc import key_slot
from redis.exceptions import ClusterCrossSlotError

from base.cache import ClusterFileBasedCache, ClusterLocMemCache

#: Two keys a cluster keeps in different slots, and two that share a hash tag (``{acme}``: the slot is computed
#: from what is between the first ``{`` and the next ``}``).
APART = ("alpha", "bravo")
TOGETHER = ("{acme}:alpha", "{acme}:bravo")


@pytest.fixture(params=["memory", "disk"])
def backend(request, tmp_path):
    """Each cache without Valkey, empty: the tests' (the process's memory) and local development's (the disk)."""

    def make(**params) -> BaseCache:
        if request.param == "memory":
            cache = ClusterLocMemCache("base-cache-tests", params)
        else:
            cache = ClusterFileBasedCache(str(tmp_path / "cache"), params)
        cache.clear()
        return cache

    return make


def slot(cache: BaseCache, key: str, version: int | None = None) -> int:
    return key_slot(cache.make_key(key, version).encode())


def test_the_keys_of_these_tests_are_where_they_say(backend):
    cache = backend()
    assert slot(cache, APART[0]) != slot(cache, APART[1])
    assert slot(cache, TOGETHER[0]) == slot(cache, TOGETHER[1])


CALLS = {
    "get_many": lambda cache, keys: cache.get_many(keys),
    "set_many": lambda cache, keys: cache.set_many(dict.fromkeys(keys, 1), 60),
    "delete_many": lambda cache, keys: cache.delete_many(keys),
}


@pytest.mark.parametrize("call", CALLS.values(), ids=CALLS.keys())
def test_a_call_on_keys_of_different_slots_is_refused_as_a_valkey_cluster_refuses_it(call, backend):
    cache = backend()
    with pytest.raises(ClusterCrossSlotError, match="same slot"):
        call(cache, list(APART))


def test_a_refused_write_writes_nothing(backend):
    cache = backend()
    with pytest.raises(ClusterCrossSlotError):
        cache.set_many({APART[0]: 1, APART[1]: 2}, 60)
    assert cache.get(APART[0]) is None and cache.get(APART[1]) is None
    cache.set(APART[0], 1)
    with pytest.raises(ClusterCrossSlotError):
        cache.delete_many(list(APART))
    assert cache.get(APART[0]) == 1


def test_keys_that_share_a_hash_tag_go_together(backend):
    cache = backend()
    assert cache.set_many({TOGETHER[0]: 1, TOGETHER[1]: 2}, 60) == []
    assert cache.get_many(iter(TOGETHER)) == {TOGETHER[0]: 1, TOGETHER[1]: 2}
    cache.delete_many(iter(TOGETHER))
    assert cache.get_many(list(TOGETHER)) == {}


@pytest.mark.parametrize("call", CALLS.values(), ids=CALLS.keys())
def test_one_key_is_one_slot(call, backend):
    call(backend(), [APART[0]])


def test_the_slot_is_the_stored_key_s_with_its_prefix_and_version(backend):
    # A cluster hashes the key Django stores (``<prefix>:<version>:<key>``), not the one the code passes: a prefix
    # with a hash tag puts every key in one slot.
    tagged = backend(KEY_PREFIX="{hub}")
    assert tagged.get_many(list(APART)) == {}
    with pytest.raises(ClusterCrossSlotError):
        backend(KEY_PREFIX="hub").get_many(list(APART), version=2)


def test_an_increment_keeps_the_key_s_expiry_as_valkey_s_incr_does(backend, monkeypatch):
    # The attempt limits count with add and incr (base.throttle): a window ends when its first call said, however
    # many calls came after.
    now = [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: now[0])
    cache = backend()
    cache.set("count", 1, 60)
    assert cache.incr("count") == 2
    assert cache.incr("count", 3) == 5
    now[0] += 59
    assert cache.get("count") == 5
    now[0] += 2
    assert cache.get("count") is None
    with pytest.raises(ValueError):
        cache.incr("count")


def test_an_increment_of_a_key_that_never_expires_leaves_it_so(backend, monkeypatch):
    now = [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: now[0])
    cache = backend()
    cache.set("generation", 0, None)
    assert cache.incr("generation") == 1
    now[0] += 10 * 365 * 86_400
    assert cache.get("generation") == 1


def test_an_increment_of_a_key_past_its_expiry_finds_nothing_to_add_to(backend, monkeypatch):
    # The key is still on disk, unread since it expired: the increment must not bring it back.
    now = [1_000_000.0]
    monkeypatch.setattr(time, "time", lambda: now[0])
    cache = backend()
    cache.set("count", 1, 60)
    now[0] += 61
    with pytest.raises(ValueError):
        cache.incr("count")
    assert cache.get("count") is None
