"""The vouchers sold: one and one of its sessions by their id, their list with their balance and expiry, whose they
are, the orphans of a deleted card and the sessions held at the till."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied
from live.operations import get

from apps.service.models.grants import Grant, GrantAdjustment
from apps.service.schemas.fields import ByIdIn, PageIn
from apps.service.schemas.grants import GrantListIn
from apps.service.schemas.sessions import SessionRefIn

from .conftest import A, HUB_DB, ctx_for, make_customer, make_grant, make_package, make_redemption, make_service, run

pytestmark = HUB_DB


# ── A record by its id, as the assistant's card names it ────────────────────────────────────────

def sold_on_the_third_of_october():
    package = make_package("Bono 5 cortes", services=[make_service("Corte")], sessions=5)
    grant = make_grant(package, make_customer("Lucía Pérez"))
    Grant.objects.filter(pk=grant.pk).update(granted_at=dt.datetime(2026, 10, 3, 12, tzinfo=dt.UTC))
    return grant


def test_a_voucher_sold_by_its_id_says_what_it_is_whose_and_when_in_the_readers_language():
    grant = sold_on_the_third_of_october()
    op = get("service.grant.get")
    spanish = op(OperationContext(scope=A, actor="t", permissions=ctx_for().permissions, language="es"), ByIdIn(id=grant.id))
    assert (spanish.id, spanish.label) == (grant.id, "Bono 5 cortes · Lucía Pérez · 3 oct 2026")
    assert run("service.grant.get", ByIdIn(id=grant.id)).label == "Bono 5 cortes · Lucía Pérez · Oct 3, 2026"
    with pytest.raises(NotFound) as error:
        run("service.grant.get", ByIdIn(id=uuid.uuid7()))
    assert error.value.code == "service.grant_not_found"


def test_a_voucher_says_the_day_it_was_sold_on_the_businesss_clock(night_elsewhere):
    grant = make_grant(make_package("Bono", services=[make_service("Corte")], sessions=5), make_customer("Lucía Pérez"))
    assert run("service.grant.get", ByIdIn(id=grant.id)).label == "Bono · Lucía Pérez · Nov 2, 2026"


def test_a_voucher_sold_says_its_owner_only_to_who_may_see_customers():
    grant = sold_on_the_third_of_october()
    without = ctx_for().permissions - {"customer.view"}
    found = get("service.grant.get")(ctx_for(permissions=without), ByIdIn(id=grant.id))
    assert found.label == "Bono 5 cortes · Oct 3, 2026"


def test_a_session_by_its_id_says_its_voucher_its_owner_and_its_service():
    grant = sold_on_the_third_of_october()
    corte = grant.package.items.get().service
    session = make_redemption(grant, corte)
    found = run("service.session.get", SessionRefIn(id=session.id), role="hub_employee")
    assert (found.id, found.grant_id, found.label) == (session.id, grant.id, "Bono 5 cortes · Lucía Pérez · Corte")
    without = ctx_for().permissions - {"customer.view"}
    assert get("service.session.get")(ctx_for(permissions=without), SessionRefIn(id=session.id)).label == "Bono 5 cortes · Corte"


def test_a_session_with_no_service_leaves_it_out_and_one_that_is_not_there_is_refused():
    session = make_redemption(sold_on_the_third_of_october())
    assert run("service.session.get", SessionRefIn(id=session.id)).label == "Bono 5 cortes · Lucía Pérez"
    with pytest.raises(NotFound) as error:
        run("service.session.get", SessionRefIn(id=uuid.uuid7()))
    assert error.value.code == "service.session_not_found"


# ── Vouchers sold ─────────────────────────────────────────────────────────────────────────────


def test_a_voucher_sold_shows_its_balance_and_expiry(tax):
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono 5", [cut], max_uses=5, validity_days=90)
    lucia = make_customer("Lucía Pérez")
    grant = make_grant(package, lucia, days_ago=10, amount=9000)
    make_redemption(grant, cut)
    make_redemption(grant, cut)
    GrantAdjustment.objects.create(
        grant=grant, uses_delta=2, days_delta=30, reason="courtesy"
    )
    GrantAdjustment.objects.create(grant=grant, uses_delta=-1, reason="correction")
    [row] = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert (row.customer_name, row.amount, row.used, row.max_uses, row.remaining) == (
        "Lucía Pérez",
        9000,
        2,
        6,
        4,
    )
    assert (
        row.uses_added,
        row.uses_removed,
        row.days_added,
        row.status,
        row.is_expired,
    ) == (2, 1, 30, "active", False)
    assert row.expires_at == grant.granted_at + dt.timedelta(days=120)
    assert (row.can_void, row.can_adjust) == (False, True)


def test_an_unlimited_voucher_has_no_remaining_and_one_without_validity_never_expires(
    tax,
):
    package = make_package("Unlimited", [make_service("Cut", tax=tax)])
    grant = make_grant(package, make_customer(), days_ago=1000)
    [row] = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert (row.max_uses, row.remaining, row.expires_at, row.is_expired) == (
        None,
        None,
        None,
        False,
    )
    assert (row.can_void, row.can_adjust, row.id) == (True, False, grant.id)


def test_an_expired_voucher_says_so():
    package = make_package("Bono", validity_days=30, max_uses=3)
    make_grant(package, make_customer(), days_ago=31)
    [row] = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert row.is_expired is True


def test_the_vouchers_of_a_customer_by_name_most_recent_first_voided_ones_included():
    package, other = make_package("Bono", max_uses=5), make_package("Other", max_uses=1)
    lucia, marta = make_customer("Lucía Pérez"), make_customer("Marta Gil")
    old = make_grant(package, lucia, days_ago=5)
    new = make_grant(
        other,
        lucia,
        days_ago=1,
        voided_at=timezone.now(),
        voided_by="boss",
        void_reason="wrong",
    )
    make_grant(package, marta)
    page = run("service.grant.list", GrantListIn(customer="Lucía Pérez"))
    assert [row.id for row in page.rows] == [new.id, old.id]
    assert (
        page.rows[0].status,
        page.rows[0].voided_by,
        page.rows[0].void_reason,
        page.rows[0].can_void,
    ) == (
        "voided",
        "boss",
        "wrong",
        False,
    )
    assert [
        row.id
        for row in run(
            "service.grant.list", GrantListIn(customer_id=lucia.id, status="active")
        ).rows
    ] == [old.id]


def test_a_customer_name_is_shown_only_to_who_may_read_customers():
    package = make_package("Bono", max_uses=5)
    make_grant(package, make_customer("Lucía"))
    permissions = {"service.view_package_balance"}
    [row] = run(
        "service.grant.list",
        GrantListIn(package_id=package.id),
        permissions=permissions,
    ).rows
    assert row.customer_name is None


def test_the_vouchers_of_a_deleted_card_lose_the_name_and_go_to_the_orphans():
    package = make_package("Bono", max_uses=5)
    gone, erased, merged, alive = (
        make_customer(name) for name in ("Gone", "Erased", "Merged", "Alive")
    )
    survivor = make_customer("Survivor")
    now = timezone.now()
    gone.deleted_at = now - dt.timedelta(days=2)
    gone.save()
    erased.deleted_at, erased.erased_at = now - dt.timedelta(days=1), now
    erased.save()
    merged.deleted_at, merged.merged_into = now, survivor
    merged.save()
    orphan_old = make_grant(package, gone)
    orphan_new = make_grant(package, erased)
    make_grant(package, erased, voided_at=now)
    make_grant(package, merged)
    make_grant(package, alive)
    page = run("service.grant.list_orphans", PageIn())
    assert [row.id for row in page.rows] == [orphan_new.id, orphan_old.id]
    assert (
        page.rows[1].customer_deleted_at,
        page.rows[1].remaining,
        page.rows[1].package_name,
    ) == (gone.deleted_at, 5, "Bono")
    rows = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert {row.customer_id: row.customer_name for row in rows}[gone.id] is None
    with pytest.raises(PermissionDenied):
        run("service.grant.list_orphans", PageIn(), role="hub_employee")


def test_the_vouchers_of_a_card_merged_into_it_show_before_the_relay_moves_them():
    # Customers flattens the chain of merged cards (one level): until the reaction to
    # customer.customer.merged moves the vouchers, they are read through the card that stays.
    package = make_package("Bono", max_uses=5)
    lucia, duplicate = make_customer("Lucía Pérez"), make_customer("Lucia P.")
    duplicate.deleted_at, duplicate.merged_into = timezone.now(), lucia
    duplicate.save()
    absorbed = make_grant(package, duplicate, days_ago=2)
    own = make_grant(package, lucia, days_ago=1)
    make_grant(package, make_customer("Marta"))
    page = run("service.grant.list", GrantListIn(customer_id=lucia.id))
    assert [row.id for row in page.rows] == [own.id, absorbed.id]
    assert run("service.grant.list", GrantListIn(customer="Lucía Pérez")).total == 2


# ── Sessions of the till (SERVICE-F22–F27) ───────────────────────────────────────────────────

def _sessions(grant, cut, **states):
    """One session of ``grant`` per state given (``held=…`` takes the hold's deadline)."""
    now = timezone.now()
    made = {}
    for name, value in states.items():
        if name == "held":
            made[name] = make_redemption(
                grant, cut, status="held", hold_until=value, order_line_id=uuid.uuid7()
            )
        else:
            made[name] = make_redemption(
                grant, cut, status=value, ended_at=now, order_line_id=uuid.uuid7()
            )
    return made


def test_a_live_hold_counts_as_used_and_a_released_expired_or_returned_session_does_not(
    tax,
):
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono 5", [cut], max_uses=5)
    grant = make_grant(package, make_customer())
    now = timezone.now()
    make_redemption(grant, cut)  # spent outside the till
    make_redemption(
        grant, cut, status="held", hold_until=now + dt.timedelta(hours=3), order_line_id=uuid.uuid7()
    )
    # A hold past its deadline no longer counts, even before the hourly task marks it.
    make_redemption(
        grant, cut, status="held", hold_until=now - dt.timedelta(minutes=1), order_line_id=uuid.uuid7()
    )
    for state in ("released", "expired", "returned"):
        make_redemption(grant, cut, status=state, ended_at=now, order_line_id=uuid.uuid7())
    [row] = run("service.grant.list", GrantListIn(package_id=package.id)).rows
    assert (row.used, row.remaining, row.can_void) == (2, 3, False)
