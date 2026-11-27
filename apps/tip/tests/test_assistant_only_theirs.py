"""An employee who asks the assistant for the tip of a colleague's sale hears that she can only see her own (hub#2688).

Without «Manage tips» one tip is read only by whoever it belongs to, and the read answers that it no longer exists.
Told nothing more, the model says the sale has no tip."""

import json

from live.operations import get

from base import assistant
from base.only_theirs import ONLY_THEIRS

from .conftest import CARD, HUB_DB, add_tip, as_user, charge, ctx_for, member

pytestmark = HUB_DB

GET = "tip.tip.get"


def answered(ctx, sale) -> dict:
    return json.loads(assistant.tools.run(ctx, get(GET), json.dumps({"sale": sale.number})).content)


def test_bea_asking_for_the_tip_of_a_colleagues_sale_hears_she_reads_only_her_own(coffee, make_user):
    user = make_user("bea", role="hub_employee")
    member("Bea", user_id=str(user.person.pk))
    sale = charge(payments=CARD, staff_id=str(member("Ana").id))
    add_tip(200, sale_id=str(sale.id))
    answer = answered(as_user(user), sale)
    assert answer["error"]["code"] == "tip.tip_not_found"
    assert answer[ONLY_THEIRS]


def test_her_own_tip_and_whoever_manages_tips_hear_nothing_of_the_kind(coffee, make_user):
    user = make_user("bea", role="hub_employee")
    sale = charge(payments=CARD, staff_id=str(member("Bea", user_id=str(user.person.pk)).id))
    add_tip(100, sale_id=str(sale.id))
    for ctx in (as_user(user), ctx_for("hub_owner")):
        answer = answered(ctx, sale)
        assert answer["amount"]
        assert ONLY_THEIRS not in answer
