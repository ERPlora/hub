"""A count of the drawer (CASH_REGISTER-F06): notes and coins added up by the server, or a typed total."""

import pytest
from live.errors import Conflict, InvalidPayload

from apps.cash_register.models import Count
from apps.cash_register.tests.conftest import HUB_DB, events, open_session, run

pytestmark = HUB_DB


# ── CASH_REGISTER-F06 Counts ────────────────────────────────────────────────────────────────────


def test_a_count_by_notes_and_coins_is_added_up_by_the_server():
    session = open_session()
    count = run(
        "cash_register.count.add",
        {
            "denominations": {"bills": {"50": 2, "5": 0}, "coins": {"0.05": 3}},
            "notes": "evening",
        },
    )
    assert (count.total, count.type, count.session_id) == (10015, "closing", session.id)
    # What is stored is what was counted: the empty boxes leave.
    assert Count.objects.get().denominations == {
        "bills": {"50": 2},
        "coins": {"0.05": 3},
    }
    assert events("cash_register.count.added") == [
        {
            "session_id": str(session.id),
            "count_id": str(count.id),
            "type": "closing",
            "total": 10015,
        }
    ]


def test_a_typed_total_prevails_over_the_notes_and_coins():
    open_session()
    count = run(
        "cash_register.count.add",
        {"type": "opening", "total": 4321, "denominations": {"bills": {"50": 1}}},
    )
    assert count.total == 4321


def test_a_note_or_coin_of_another_currency_is_refused():
    open_session()
    with pytest.raises(InvalidPayload) as refused:
        run("cash_register.count.add", {"denominations": {"bills": {"25": 1}}})
    assert "denominations" in refused.value.fields


def test_a_closed_session_is_not_counted():
    session = open_session()
    run("cash_register.session.close", {"closing_balance": 10000})
    with pytest.raises(Conflict) as refused:
        run("cash_register.count.add", {"session_id": str(session.id), "total": 100})
    assert refused.value.code == "cash_register.session_not_open"
