"""Writes of the vouchers sold: grant one to a customer, void it, adjust it and spend its sessions."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound

from apps.service.models.grants import Grant, GrantAdjustment, Redemption
from apps.service.schemas.grants import RedeemIn

from .conftest import (
    HUB_DB, events, make_customer, make_grant, make_member, make_package, make_redemption, make_service, payload, run,
)

pytestmark = HUB_DB


def test_grant_a_voucher_to_a_customer_freezing_its_terms(tax):
    package = make_package(
        "Bono 5", [make_service("Cut", tax=tax)], max_uses=5, validity_days=90
    )
    lucia = make_customer("Lucía Pérez")
    out = run(
        "service.grant.create",
        {
            "package": "Bono 5",
            "customer": "Lucía Pérez",
            "amount": 9000,
            "note": "paid cash",
        },
        role="hub_employee",
    )
    grant = Grant.objects.get()
    assert (
        out.customer_id,
        out.max_uses,
        out.remaining,
        out.amount,
        out.status,
        out.source,
    ) == (lucia.id, 5, 5, 9000, "active", "manual")
    assert (grant.validity_days, grant.created_by, grant.note) == (
        90,
        "tester",
        "paid cash",
    )
    assert out.expires_at == grant.granted_at + dt.timedelta(days=90)
    assert payload("service.grant.granted") == {
        "id": str(grant.id),
        "package_id": str(package.id),
        "customer_id": str(lucia.id),
    }


def test_a_voucher_cannot_be_granted_from_a_deleted_or_inactive_package():
    lucia = make_customer("Lucía")
    for package in (
        make_package("Gone", is_deleted=True),
        make_package("Off", is_active=False),
    ):
        with pytest.raises(NotFound) as missing:
            run(
                "service.grant.create",
                {"package_id": str(package.id), "customer_id": str(lucia.id)},
            )
        assert missing.value.message == "That package does not exist in this business."


def test_a_voucher_bought_earlier_counts_its_expiry_from_then():
    package = make_package("Bono", max_uses=5, validity_days=30)
    make_customer("Lucía")
    bought = timezone.now() - dt.timedelta(days=40)
    data = {"package_id": str(package.id), "customer": "Lucía", "granted_at": bought.isoformat()}
    out = run("service.grant.create", data)
    assert out.is_expired is True


def test_void_an_untouched_voucher_with_its_reason():
    grant = make_grant(make_package("Bono", max_uses=5), make_customer())
    out = run(
        "service.grant.void",
        {"id": str(grant.id), "reason": "sold to the wrong customer"},
    )
    grant.refresh_from_db()
    assert (
        out.status,
        grant.voided_by,
        grant.void_reason,
        grant.voided_at is not None,
    ) == ("voided", "tester", "sold to the wrong customer", True)
    assert payload("service.grant.voided") == {
        "id": str(grant.id),
        "package_id": str(grant.package_id),
        "customer_id": str(grant.customer_id),
    }
    with pytest.raises(Conflict) as again:
        run("service.grant.void", {"id": str(grant.id), "reason": "twice"})
    assert (again.value.code, again.value.message) == (
        "service.grant_already_voided",
        "That voucher was already voided.",
    )


def test_a_voucher_already_used_is_not_voided():
    grant = make_grant(make_package("Bono", max_uses=5), make_customer())
    make_redemption(grant)
    with pytest.raises(Conflict) as used:
        run("service.grant.void", {"id": str(grant.id), "reason": "oops"})
    assert (used.value.code, used.value.message) == (
        "service.grant_in_use",
        "That voucher was already used: it cannot be voided.",
    )
    assert events() == []


def test_adjust_gives_sessions_and_days_and_revives_a_spent_voucher():
    grant = make_grant(
        make_package("Bono", max_uses=1, validity_days=30), make_customer(), days_ago=40
    )
    make_redemption(grant)
    out = run(
        "service.grant.adjust",
        {
            "id": str(grant.id),
            "uses_delta": 2,
            "days_delta": 30,
            "reason": "we were closed",
        },
    )
    adjustment = GrantAdjustment.objects.get()
    assert (out.remaining, out.is_expired, out.uses_added, out.days_added) == (
        2,
        False,
        2,
        30,
    )
    assert (adjustment.actor, adjustment.reason) == ("tester", "we were closed")
    assert payload("service.grant.adjusted") == {
        "id": str(grant.id),
        "uses_delta": 2,
        "days_delta": 30,
    }


def test_adjust_takes_sessions_but_never_more_than_are_left():
    grant = make_grant(make_package("Bono", max_uses=3), make_customer())
    make_redemption(grant)
    with pytest.raises(Conflict) as below:
        run(
            "service.grant.adjust",
            {"id": str(grant.id), "uses_delta": -3, "reason": "typo"},
        )
    assert (below.value.code, below.value.message) == (
        "service.grant_adjust_below_used",
        "You cannot take away more sessions than the customer has left.",
    )
    out = run(
        "service.grant.adjust",
        {"id": str(grant.id), "uses_delta": -2, "reason": "typo"},
    )
    assert (out.remaining, out.uses_removed) == (0, 2)


def test_adjust_refuses_what_the_voucher_does_not_have():
    unlimited = make_grant(
        make_package("Unlimited", validity_days=30), make_customer("A")
    )
    forever = make_grant(make_package("Forever", max_uses=5), make_customer("B"))
    voided = make_grant(
        make_package("Voided", max_uses=5), make_customer("C"), voided_at=timezone.now()
    )
    cases = [
        (unlimited, {"uses_delta": 1}, "service.grant_unlimited"),
        (forever, {"days_delta": 1}, "service.grant_no_expiry"),
        (voided, {"uses_delta": 1}, "service.grant_already_voided"),
    ]
    for grant, change, code in cases:
        with pytest.raises(Conflict) as refused:
            run("service.grant.adjust", {"id": str(grant.id), "reason": "x", **change})
        assert refused.value.code == code
    assert not GrantAdjustment.objects.exists()


def test_redeem_a_session_of_a_service_the_voucher_covers(tax):
    cut = make_service("Cut", tax=tax)
    grant = make_grant(make_package("Bono", [cut], max_uses=2), make_customer())
    sale = uuid.uuid7()
    out = run(
        "service.grant.redeem",
        {"id": str(grant.id), "service": "Cut", "sale_id": str(sale), "note": "Friday"},
        role="hub_employee",
    )
    session = Redemption.objects.get()
    assert (
        out.remaining,
        out.service_name,
        session.sale_id,
        session.actor,
        session.note,
    ) == (1, "Cut", sale, "tester", "Friday")
    assert payload("service.grant.redeemed") == {
        "id": str(grant.id),
        "redemption_id": str(session.id),
        "service_id": str(cut.id),
    }


def test_a_session_spent_outside_the_till_says_who_did_it(tax):
    # flow: SERVICE-F21 (hub#770): by name, as the assistant says it, or by id, as the API does.
    cut = make_service("Cut", tax=tax)
    ana, bea = make_member("Ana", "López"), make_member("Bea", "Ruiz")
    grant = make_grant(make_package("Bono", [cut], max_uses=3), make_customer())
    by_name = run(
        "service.grant.redeem", {"id": str(grant.id), "member": "Ana"}, role="hub_employee"
    )
    by_id = run("service.grant.redeem", {"id": str(grant.id), "member_id": str(bea.id)})
    nobody = run("service.grant.redeem", {"id": str(grant.id)})
    assert [
        (Redemption.objects.get(pk=out.id).member_id, out.member_id, out.member_name)
        for out in (by_name, by_id, nobody)
    ] == [(ana.id, ana.id, "Ana López"), (bea.id, bea.id, "Bea Ruiz"), (None, None, None)]


def test_a_session_for_a_professional_who_is_not_in_the_team_is_not_spent(tax):
    cut = make_service("Cut", tax=tax)
    gone = make_member("Eva", "Gil", status="terminated")
    make_member("Ana", "López"), make_member("Ana", "Ruiz")
    grant = make_grant(make_package("Bono", [cut], max_uses=3), make_customer())
    for said, refusal in (
        ({"member_id": str(uuid.uuid7())}, NotFound),
        ({"member_id": str(gone.id)}, NotFound),
        ({"member": "Ana"}, Conflict),
    ):
        with pytest.raises(refusal):
            run("service.grant.redeem", {"id": str(grant.id), **said})
    assert not Redemption.objects.exists()
    assert events() == []


def test_a_session_is_refused_with_the_real_reason(tax):
    cut, shampoo = make_service("Cut", tax=tax), make_service("Shampoo", tax=tax)
    package = make_package("Bono", [cut], max_uses=1, validity_days=30)
    spent = make_grant(package, make_customer("A"))
    make_redemption(spent)
    cases = [
        (
            make_grant(package, make_customer("B"), voided_at=timezone.now()),
            {},
            "service.grant_voided",
            "This voucher was voided: it can no longer be used.",
        ),
        (
            make_grant(package, make_customer("C"), days_ago=31),
            {},
            "service.grant_expired",
            "This voucher has expired.",
        ),
        (spent, {}, "service.grant_no_uses_left", "This voucher has no sessions left."),
        (
            make_grant(package, make_customer("D")),
            {"service_id": str(shampoo.id)},
            "service.grant_does_not_cover_service",
            "This voucher does not cover that service. A voucher of haircuts pays for haircuts, not for the shampoo.",
        ),
    ]
    for grant, service, code, message in cases:
        with pytest.raises(Conflict) as refused:
            run("service.grant.redeem", {"id": str(grant.id), **service})
        assert (refused.value.code, refused.value.message) == (code, message)
    assert Redemption.objects.count() == 1


def test_a_voucher_of_a_deleted_package_is_still_spent(tax):
    cut = make_service("Cut", tax=tax)
    grant = make_grant(
        make_package("Bono", [cut], max_uses=2, is_deleted=True), make_customer()
    )
    assert (
        run(
            "service.grant.redeem", {"id": str(grant.id), "service_id": str(cut.id)}
        ).remaining
        == 1
    )


def test_an_unknown_voucher_sold_is_not_found():
    with pytest.raises(NotFound) as missing:
        run("service.grant.redeem", RedeemIn(id=uuid.uuid7()))
    assert (missing.value.code, missing.value.message) == (
        "service.grant_not_found",
        "That voucher sale does not exist in this business.",
    )


def test_who_acted_is_kept_by_the_name_a_person_reads(make_user):
    # «Voided by {who}», «Given by {who}»: the account's full name, else what goes before the «@» of its email.
    boss = make_user("saas:01a1355a")
    boss.first_name, boss.last_name = "Ana", "López"
    boss.save()
    grant = make_grant(make_package("Bono", max_uses=5), make_customer())
    run("service.grant.adjust", {"id": str(grant.id), "uses_delta": 1, "reason": "courtesy"}, actor=boss)
    run("service.grant.void", {"id": str(make_grant(make_package("Other", max_uses=1), make_customer("B")).id), "reason": "x"}, actor=boss)
    assert GrantAdjustment.objects.get().actor == "Ana López"
    assert Grant.objects.exclude(voided_by="").get().voided_by == "Ana López"
    mail = make_user("saas:02b", host=None)
    mail.email = "eva@example.com"
    mail.save()
    run("service.grant.redeem", {"id": str(grant.id)}, actor=mail)
    assert Redemption.objects.get().actor == "eva"
