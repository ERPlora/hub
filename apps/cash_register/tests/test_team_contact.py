"""Who opens, counts, adds a movement to and closes a shift never shows a colleague's email (BASE-F119).

The drawer keeps who did each thing by the name a colleague reads: the account's name, else what goes before the «@»
of its email, never the address. An employee sees no colleague's contact details; the manager reads the same name.
The shifts saved with an address before are cleaned once by the app's migration (``test_migrations``).
"""

import pytest

from apps.flow.tests.test_api import get, post
from apps.cash_register.models import Count, Movement, Session
from base.tests.colleagues import NAMELESS, SHOWN, signed_in

from .conftest import HUB_DB

pytestmark = HUB_DB


@pytest.fixture(params=list(NAMELESS.values()), ids=list(NAMELESS))
def zoe(request):
    """Zoe, a cashier whose account has no name of its own: her device."""
    return signed_in("zoe", **request.param)


def created(response):
    assert response.status_code == 201, response.content
    return response.json()


@pytest.mark.parametrize("role", ["hub_employee", "hub_manager"])
def test_who_opens_counts_and_adds_a_movement_is_named_without_their_address(zoe, role):
    shift = created(post(zoe, "/cash_register/sessions/open", {"opening_balance": 0}))
    created(post(zoe, "/cash_register/movements", {"type": "in", "amount": 500, "description": "Change"}))
    created(post(zoe, "/cash_register/counts", {"denominations": {"bills": {"5": 1}}}))
    reader = signed_in("reader", role)
    listed = [row["opened_by"] for row in get(reader, "/cash_register/sessions").json()["rows"]]
    detail = get(reader, "/cash_register/sessions/detail", session_id=shift["id"]).json()["opened_by"]
    moves = [row["created_by"] for row in get(reader, "/cash_register/movements", session_id=shift["id"]).json()["rows"]]
    counts = [row["counted_by"] for row in get(reader, "/cash_register/counts", session_id=shift["id"]).json()["rows"]]
    assert (listed, detail, moves, counts) == ([SHOWN], SHOWN, [SHOWN], [SHOWN])
    saved = (Session.objects.get().opened_by, Movement.objects.get().created_by, Count.objects.get().counted_by)
    assert saved == (SHOWN, SHOWN, SHOWN)


def test_who_closes_a_colleague_s_shift_is_named_without_their_address(zoe):
    ana = signed_in("ana")
    shift = created(post(ana, "/cash_register/sessions/open", {"opening_balance": 0}))
    closed = post(zoe, "/cash_register/sessions/close", {"session_id": shift["id"], "closing_balance": 0})
    assert closed.status_code == 200, closed.content
    detail = get(ana, "/cash_register/sessions/detail", session_id=shift["id"]).json()["closed_by"]
    assert (detail, Session.objects.get().closed_by) == (SHOWN, SHOWN)


def test_a_named_colleague_keeps_their_name(db):
    luis = signed_in("luis", first_name="Luis", last_name="García", email="luis@example.com")
    created(post(luis, "/cash_register/sessions/open", {"opening_balance": 0}))
    moved = created(post(luis, "/cash_register/movements", {"type": "in", "amount": 500, "description": "Change"}))
    assert moved["created_by"] == "Luis García"
