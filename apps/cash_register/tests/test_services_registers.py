"""The drawers (CASH_REGISTER-F02): created with a name no other drawer has, renamed or deactivated."""

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.cash_register.models import Register
from apps.cash_register.tests.conftest import HUB_DB, ctx_for, events, run

pytestmark = HUB_DB


# ── CASH_REGISTER-F02 Drawers ───────────────────────────────────────────────────────────────────


def test_a_drawer_is_created_with_its_name():
    drawer = run("cash_register.register.create", {"name": " Bar "})
    assert (drawer.name, drawer.is_active) == ("Bar", True)
    assert Register.objects.get().created_by == "tester"
    assert events("cash_register.register.created") == [{"id": str(drawer.id)}]


def test_two_drawers_never_share_a_name():
    run("cash_register.register.create", {"name": "Bar"})
    with pytest.raises(Conflict) as refused:
        run("cash_register.register.create", {"name": "BAR"})
    assert refused.value.code == "cash_register.register_exists"
    assert "name" in refused.value.fields


def test_a_drawer_is_renamed_and_deactivated_by_its_name():
    run("cash_register.register.create", {"name": "Bar"})
    renamed = run(
        "cash_register.register.update", {"register_name": "bar", "name": "Terrace"}
    )
    assert renamed.name == "Terrace"
    off = run(
        "cash_register.register.update",
        {"register_id": str(renamed.id), "is_active": False},
    )
    assert off.is_active is False
    assert len(events("cash_register.register.updated")) == 2


def test_renaming_to_another_drawers_name_is_refused():
    run("cash_register.register.create", {"name": "Bar"})
    run("cash_register.register.create", {"name": "Terrace"})
    with pytest.raises(Conflict) as refused:
        run(
            "cash_register.register.update", {"register_name": "Terrace", "name": "bar"}
        )
    assert refused.value.code == "cash_register.register_exists"


def test_an_unknown_drawer_is_not_found():
    with pytest.raises(NotFound) as refused:
        run(
            "cash_register.register.update",
            {"register_name": "Nope", "is_active": False},
        )
    assert refused.value.code == "cash_register.register_not_found"


def test_drawers_are_the_admins():
    with pytest.raises(PermissionDenied):
        run("cash_register.register.create", {"name": "Bar"}, ctx_for("hub_employee"))
