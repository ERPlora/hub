"""The accounts a record can hang from: the «Hub user» selector of the form (STAFF-F03)."""

import pytest
from live.errors import InvalidPayload, PermissionDenied
from live.operations import get

from apps.staff.queries.accounts import list_accounts
from apps.staff.schemas.accounts import AccountCheckIn, AccountListIn
from base.services.sessions import ensure_hub_user

from .conftest import HUB_DB, A, B, ctx_for

pytestmark = HUB_DB


def accounts(role="hub_admin", **params):
    return list_accounts(ctx_for(role), AccountListIn(**params))


def test_the_accounts_with_access_to_this_business(make_user):
    marta = make_user("saas:1", host=A.key, role="hub_manager", first_name="Marta")
    eva = make_user("saas:2", host=A.key, role="hub_employee")
    eva.email = "eva@shop.es"
    eva.save()
    ensure_hub_user(eva)  # her next entry brings her person up to date
    make_user("saas:3", host=B.key, first_name="Other business")
    gone = make_user("saas:4", host=A.key, first_name="Deactivated")
    gone.is_active = False
    gone.save()

    page = accounts()

    assert [row.model_dump() for row in page.rows] == [
        {"user_id": eva.person.id, "name": "eva@shop.es"},
        {"user_id": marta.person.id, "name": "Marta"},
    ]
    assert page.total == 2
    assert [row.user_id for row in accounts(search="MAR").rows] == [marta.person.id]
    assert [row.user_id for row in accounts(search="shop.es").rows] == [eva.person.id]


def test_one_account_by_its_user_to_name_the_one_a_record_hangs_from(make_user):
    marta = make_user("saas:1", host=A.key, role="hub_manager", first_name="Marta")
    make_user("saas:2", host=A.key, role="hub_employee", first_name="Eva")
    elsewhere = make_user("saas:3", host=B.key, first_name="Other business")
    gone = make_user("saas:4", host=A.key, first_name="Deactivated")
    gone.is_active = False
    gone.save()

    assert [row.name for row in accounts(user_id=marta.person.id).rows] == ["Marta"]
    # Without access to this business (another one's, or deactivated): nothing to name.
    assert accounts(user_id=elsewhere.person.id).rows == []
    assert accounts(user_id=gone.person.id).rows == []


def test_accounts_for_whoever_adds_or_edits_records():
    assert accounts(role="hub_manager").total == 0
    for permissions in ({"staff.view", "staff.add_member"}, {"staff.view", "staff.change_member"}):
        assert get("staff.account.list")(ctx_for(permissions=permissions), AccountListIn()).total == 0
    with pytest.raises(PermissionDenied):
        accounts(role="hub_employee")


def test_the_account_a_record_would_hang_from_is_checked_for_whoever_adds_or_edits_records(make_user):
    marta = make_user("saas:1", host=A.key, role="hub_manager", first_name="Marta")
    elsewhere = make_user("saas:3", host=B.key, first_name="Other business")
    check = get("staff.account.check")

    assert check(ctx_for(), AccountCheckIn(user_id=marta.person.id)).name == "Marta"
    assert check(ctx_for(), AccountCheckIn()).id is None
    with pytest.raises(InvalidPayload) as refused:
        check(ctx_for(), AccountCheckIn(user_id=elsewhere.person.id))
    assert set(refused.value.fields) == {"user_id"}
    with pytest.raises(PermissionDenied):
        check(ctx_for("hub_employee"), AccountCheckIn(user_id=marta.person.id))
