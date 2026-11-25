"""The counters of a database cloned from its template.

PostgreSQL writes a sequence to the WAL 32 values ahead and hands out the next ones from memory. ``CREATE DATABASE …
TEMPLATE`` copies that page from the template, so those values were written only in the template's WAL: once the clone's
page is rebuilt from its own (a crash; on Aurora, the page leaving the cache), its counter goes back to the value it was
cloned at and hands out again ids its rows already have. The counter of ``django_migrations`` that went back in hubs
cloned before this is put right by the migrator (``test_migrator_schema.py``).
"""

import uuid
from collections.abc import Iterator

import pytest
from psycopg import errors, sql

from base.tenancy import names, ops, sequences
from base.tenancy.tests import hubs


def counters(name: str) -> dict[str, tuple[int, int]]:
    """``{sequence: (its last value, how many more it hands out before it writes to the WAL)}`` of every sequence of the
    database ``name`` that has handed out a value."""
    with hubs._maintenance(name) as conn:
        used = [row[0] for row in conn.execute("SELECT sequencename FROM pg_sequences WHERE last_value IS NOT NULL")]
        state = sql.SQL("SELECT last_value, log_cnt FROM {}")
        return {seq: conn.execute(state.format(sql.Identifier(seq))).fetchone() for seq in used}


@pytest.fixture
def template(hub_databases) -> Iterator[str]:
    """A template of its own: some of its counters have handed out a value, and at least one has not."""
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    with hubs.clone_of_the_template(hub_databases, name):
        with hubs._maintenance(name) as conn:
            conn.execute("SELECT nextval(sequencename::regclass) FROM pg_sequences WHERE last_value IS NULL LIMIT 2")
            assert conn.execute("SELECT count(*) FROM pg_sequences WHERE last_value IS NULL").fetchone()[0] > 0
        yield name


@pytest.fixture
def clone(hub_databases) -> Iterator[str]:
    """The name of the database a test clones; dropped after it."""
    name = names.hub_db_name(hub_databases.control, uuid.uuid7())
    yield name
    ops.drop_database(name)


def with_no_credit(of_the_template: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    assert len(of_the_template) > 1 and any(credit for _last, credit in of_the_template.values()), of_the_template
    return {seq: (last, 0) for seq, (last, _credit) in of_the_template.items()}


def test_a_clone_hands_out_no_counter_value_its_own_wal_does_not_hold(template, clone):
    """Right after the clone, every counter goes on from its template's value with nothing left on the template's
    credit: the first value it hands out is written in its own WAL."""
    expected = with_no_credit(counters(template))

    assert ops.clone_database(clone, template=template) is True

    assert counters(clone) == expected


def test_a_clone_cut_short_before_its_counters_were_written_gets_them_written_the_second_time(template, clone):
    expected = with_no_credit(counters(template))
    with hubs._maintenance() as conn:
        conn.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(sql.Identifier(clone), sql.Identifier(template)))
    assert counters(clone) != expected

    assert ops.clone_database(clone, template=template) is False

    assert counters(clone) == expected


def test_counters_the_server_refuses_to_write_are_a_readable_failure(template, clone, monkeypatch):
    def refuse(conn):
        raise errors.InsufficientPrivilege("permission denied for sequence")

    monkeypatch.setattr(sequences, "write_down", refuse)

    with pytest.raises(ops.DatabaseOpsError, match=f"counters of '{clone}'.*permission denied"):
        ops.clone_database(clone, template=template)
