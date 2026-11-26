"""«Quita la paella de la carta» (hub#2655): the model first asked to delete a menu with data that do not fit, then to
take the dish off; the person confirmed that one, and its receipt is the only one under the answer (BASE-F97): nothing
about Menus, which nobody asked for.
"""

from functools import partial

from apps.combo.tests.conftest import HUB_DB, ctx_for, make_product
from base.tests.test_assistant_yes_for_its_card import the_model_hears, turn_as, yes_to
from base.tests.test_services_assistant import call

pytestmark = HUB_DB


def test_taking_the_paella_off_the_menu_leaves_only_its_own_receipt():
    paella = make_product("Paella")
    owner = ctx_for("hub_admin")
    slip = call("combo.combo.delete", {}, call_id="c1")
    off = call("inventory.product.update", {"id": str(paella.id), "is_active": False}, call_id="c2")

    drawn = turn_as(owner, slip, off)
    assert the_model_hears(drawn)["code"] == "invalid_payload"
    assert (drawn["confirm"]["operation"], drawn["executed"]) == ("inventory.product.update", [])

    done = yes_to(drawn, turn_of=partial(turn_as, owner))
    assert [(row["name"], row["outcome"]) for row in done["executed"]] == [("inventory.product.update", "ok")]
    paella.refresh_from_db()
    assert paella.is_active is False
