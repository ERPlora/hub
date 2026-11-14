"""How long a move can keep a business closed, by the size of its database.

The business is closed while its database is copied: both halves of the copy (the dump to the bucket and the restore
from it) at the slowest rate a copy is counted at, each within its own time limit, in whole minutes.
"""

import datetime as dt

from base.tenancy import move


def seconds_of_copy(seconds: int) -> int:
    """The size of a database each half of whose copy takes ``seconds`` at the slowest rate."""
    return seconds * move.COPY_SLOWEST_BYTES_PER_SECOND


def test_a_small_database_closes_it_for_both_halves_of_its_copy_in_whole_minutes():
    assert move.longest_closure(seconds_of_copy(30)) == dt.timedelta(minutes=1)
    assert move.longest_closure(seconds_of_copy(31)) == dt.timedelta(minutes=2)
    assert move.longest_closure(seconds_of_copy(20 * 60)) == dt.timedelta(minutes=40)


def test_an_empty_database_still_closes_it_for_a_minute():
    assert move.longest_closure(0) == dt.timedelta(minutes=1)


def test_a_larger_database_closes_it_for_longer():
    smaller, larger = move.longest_closure(10 * 1024**3), move.longest_closure(20 * 1024**3)

    assert dt.timedelta(minutes=30) < smaller < larger < dt.timedelta(hours=2)


def test_never_longer_than_the_time_limit_of_both_halves():
    limit = dt.timedelta(seconds=2 * move.COPY_TIMEOUT_SECONDS)

    assert move.longest_closure(seconds_of_copy(move.COPY_TIMEOUT_SECONDS)) == limit
    assert move.longest_closure(500 * 1024**3) == limit


def test_a_size_not_known_is_counted_as_the_largest():
    assert move.longest_closure(None) == dt.timedelta(seconds=2 * move.COPY_TIMEOUT_SECONDS)


def test_follows_the_time_limit_of_the_copy(monkeypatch):
    monkeypatch.setattr(move, "COPY_TIMEOUT_SECONDS", 30 * 60)

    assert move.longest_closure(None) == dt.timedelta(hours=1)
    assert move.longest_closure(500 * 1024**3) == dt.timedelta(hours=1)
