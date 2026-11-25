"""How a person names a zone, a table or a check (the assistant, the voice): by id, else an exact name or number, else
the only one that contains it; several are refused naming them, and none is not found.
"""

import uuid

import pytest
from live.errors import Conflict, NotFound

from .conftest import HUB_DB, make_session, make_table, make_zone, run

pytestmark = [HUB_DB, pytest.mark.usefixtures("noon")]


def test_a_zone_is_named_by_its_name_and_an_ambiguous_one_says_which():
    zone = make_zone("Terrace")
    make_zone("Terrace bar")
    assert run("table.zone.get", {"zone": "terrace"}).id == zone.id
    with pytest.raises(Conflict) as refused:
        run("table.zone.get", {"zone": "erra"})
    assert refused.value.code == "table.zone_ambiguous"
    with pytest.raises(NotFound) as missing:
        run("table.zone.get", {"id": str(uuid.uuid7())})
    assert missing.value.code == "table.zone_not_found"


def test_a_table_is_named_by_its_number_and_its_zone_when_the_number_repeats():
    room, terrace = make_zone("Dining room"), make_zone("Terrace")
    inside = make_table("4", zone=room)
    outside = make_table("4", zone=terrace)
    make_table("14", zone=room)
    with pytest.raises(Conflict) as refused:
        run("table.table.get", {"table": "4"})
    assert refused.value.code == "table.table_ambiguous"
    assert "Terrace" in refused.value.message
    assert run("table.table.get", {"table": "4", "zone": "terrace"}).id == outside.id
    assert (
        run("table.table.get", {"table": " 4", "zone": "Dining room"}).id == inside.id
    )
    with pytest.raises(NotFound) as missing:
        run("table.table.get", {"table": "99"})
    assert missing.value.code == "table.table_not_found"


def test_a_check_is_named_by_its_table_and_a_split_table_asks_which():
    table = make_table("4", zone=make_zone())
    first = make_session(table)
    assert run("table.session.get", {"table": "4"}).id == first.id
    make_session(table, split_from=first)
    with pytest.raises(Conflict) as refused:
        run("table.session.get", {"table": "4"})
    assert refused.value.code == "table.session_ambiguous"
    with pytest.raises(NotFound) as missing:
        run("table.session.get", {"id": str(uuid.uuid7())})
    assert missing.value.code == "table.session_not_found"
