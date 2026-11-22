"""Who records, approves and cancels a payment never shows a colleague's email (BASE-F119).

Payments keep who did each step by the name a colleague reads: the account's name, else what goes before the «@» of
its email, never the address. An employee sees no colleague's contact details; the manager reads the same name. The
payments saved with an address before are cleaned once by the app's migration (``test_migrations``).
"""

import pytest
from live.context import system_context
from live.operations import get as operation

from apps.flow.tests.test_api import get, post
from apps.payment.models import Payment
from base.tests.team_contact import NAMELESS, NAMELESS_IDS, SHOWN, signed_in

from .conftest import HUB_DB, A

pytestmark = HUB_DB

ACTORS = ("created_by", "updated_by", "approved_by", "cancelled_by")


@pytest.fixture(params=NAMELESS, ids=NAMELESS_IDS)
def zoe(request):
    """Zoe, a manager whose account has no name of its own, with a method to pay by: her device."""
    op = operation("payment.method.create")
    op(system_context(A), op.input.model_validate({"name": "Bank", "method_type": "transfer"}))
    return signed_in("zoe", "hub_manager", **request.param)[1]


def recorded(client, beneficiary: str) -> str:
    made = post(
        client,
        "/payment/payments",
        {"payment_date": "2026-11-22", "amount": 1000, "beneficiary_name": beneficiary, "method": "Bank"},
    )
    assert made.status_code == 201, made.content
    return made.json()["id"]


@pytest.mark.parametrize("role", ["hub_employee", "hub_manager"])
def test_who_records_approves_or_cancels_a_payment_is_named_without_their_address(zoe, role):
    approved = post(zoe, "/payment/payments/approve", {"id": recorded(zoe, "Bakery")})
    cancelled = post(zoe, "/payment/payments/cancel", {"id": recorded(zoe, "Florist"), "reason": "Twice"})
    assert (approved.status_code, cancelled.status_code) == (200, 200), (approved.content, cancelled.content)
    _, reader = signed_in("reader", role)
    rows = {row["beneficiary_name"]: row for row in get(reader, "/payment/payments").json()["rows"]}
    shown = {name: {field: row[field] for field in ACTORS if row[field]} for name, row in rows.items()}
    assert shown == {
        "Bakery": {"created_by": SHOWN, "updated_by": SHOWN, "approved_by": SHOWN},
        "Florist": {"created_by": SHOWN, "updated_by": SHOWN, "cancelled_by": SHOWN},
    }
    saved = {value for payment in Payment.objects.values(*ACTORS) for value in payment.values() if value}
    assert saved == {SHOWN}


def test_a_named_colleague_keeps_their_name(zoe):
    _, luis = signed_in("luis", "hub_manager", first_name="Luis", last_name="García", email="luis@example.com")
    payment = get(luis, "/payment/payments/detail", id=recorded(luis, "Bakery")).json()
    assert payment["created_by"] == "Luis García"
