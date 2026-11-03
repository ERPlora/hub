"""``base.cache.ClusterLocMemCache``: this process's memory, refusing what a Valkey cluster refuses.

In AWS the cache is a Valkey cluster (ElastiCache Serverless): a call on several keys (``get_many``'s ``MGET``,
``delete_many``'s ``DEL``, ``set_many``'s ``MULTI``) whose keys hash to different slots is answered ``CROSSSLOT``
(hub#440: the PIN limit read its count and the end of its window in one ``get_many``, was refused on every call and
stepped aside). Local development and the tests keep the cache in memory and refuse the same calls with redis-py's
own error, so what breaks in AWS breaks here first.
"""

import pytest
from redis.crc import key_slot
from redis.exceptions import ClusterCrossSlotError

from base.cache import ClusterLocMemCache

#: Two keys a cluster keeps in different slots, and two that share a hash tag (``{acme}``: the slot is computed
#: from what is between the first ``{`` and the next ``}``).
APART = ("alpha", "bravo")
TOGETHER = ("{acme}:alpha", "{acme}:bravo")


def backend(**params) -> ClusterLocMemCache:
    cache = ClusterLocMemCache("base-cache-tests", params)
    cache.clear()
    return cache


def slot(cache: ClusterLocMemCache, key: str, version: int | None = None) -> int:
    return key_slot(cache.make_key(key, version).encode())


def test_the_keys_of_these_tests_are_where_they_say():
    cache = backend()
    assert slot(cache, APART[0]) != slot(cache, APART[1])
    assert slot(cache, TOGETHER[0]) == slot(cache, TOGETHER[1])


CALLS = {
    "get_many": lambda cache, keys: cache.get_many(keys),
    "set_many": lambda cache, keys: cache.set_many(dict.fromkeys(keys, 1), 60),
    "delete_many": lambda cache, keys: cache.delete_many(keys),
}


@pytest.mark.parametrize("call", CALLS.values(), ids=CALLS.keys())
def test_a_call_on_keys_of_different_slots_is_refused_as_a_valkey_cluster_refuses_it(call):
    cache = backend()
    with pytest.raises(ClusterCrossSlotError, match="same slot"):
        call(cache, list(APART))


def test_a_refused_write_writes_nothing():
    cache = backend()
    with pytest.raises(ClusterCrossSlotError):
        cache.set_many({APART[0]: 1, APART[1]: 2}, 60)
    assert cache.get(APART[0]) is None and cache.get(APART[1]) is None
    cache.set(APART[0], 1)
    with pytest.raises(ClusterCrossSlotError):
        cache.delete_many(list(APART))
    assert cache.get(APART[0]) == 1


def test_keys_that_share_a_hash_tag_go_together():
    cache = backend()
    assert cache.set_many({TOGETHER[0]: 1, TOGETHER[1]: 2}, 60) == []
    assert cache.get_many(iter(TOGETHER)) == {TOGETHER[0]: 1, TOGETHER[1]: 2}
    cache.delete_many(iter(TOGETHER))
    assert cache.get_many(list(TOGETHER)) == {}


@pytest.mark.parametrize("call", CALLS.values(), ids=CALLS.keys())
def test_one_key_is_one_slot(call):
    call(backend(), [APART[0]])


def test_the_slot_is_the_stored_key_s_with_its_prefix_and_version():
    # A cluster hashes the key Django stores (``<prefix>:<version>:<key>``), not the one the code passes: a prefix
    # with a hash tag puts every key in one slot.
    tagged = backend(KEY_PREFIX="{hub}")
    assert tagged.get_many(list(APART)) == {}
    with pytest.raises(ClusterCrossSlotError):
        backend(KEY_PREFIX="hub").get_many(list(APART), version=2)
