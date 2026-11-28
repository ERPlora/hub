"""The checks of a voucher sold: whether it can be voided, adjusted or spent, and why not."""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import NotFound

from apps.service.schemas.fields import ByIdIn
from apps.service.schemas.grant_checks import RedeemCheckIn

from .conftest import HUB_DB, make_customer, make_grant, make_package, make_redemption, make_service, run

pytestmark = HUB_DB


def test_the_void_check_says_why_a_voucher_cannot_be_voided():
    package = make_package("Bono", max_uses=5)
    fresh, used = (
        make_grant(package, make_customer("A")),
        make_grant(package, make_customer("B")),
    )
    voided = make_grant(package, make_customer("C"), voided_at=timezone.now())
    make_redemption(used)
    check = lambda grant: run("service.grant.void_check", ByIdIn(id=grant.id))  # noqa: E731
    assert (check(fresh).voidable, check(fresh).reason) == (True, "")
    assert (check(used).voidable, check(used).reason, check(used).used) == (
        False,
        "in_use",
        1,
    )
    assert (check(voided).voidable, check(voided).reason) == (False, "already_voided")
    with pytest.raises(NotFound) as missing:
        run("service.grant.void_check", ByIdIn(id=uuid.uuid7()))
    assert missing.value.code == "service.grant_not_found"


def test_the_adjust_check_says_what_can_be_adjusted():
    limited = make_grant(make_package("Limited", max_uses=5), make_customer("A"))
    dated = make_grant(make_package("Dated", validity_days=30), make_customer("B"))
    voided = make_grant(
        make_package("Voided", max_uses=1), make_customer("C"), voided_at=timezone.now()
    )
    check = lambda grant: run("service.grant.adjust_check", ByIdIn(id=grant.id))  # noqa: E731
    assert (
        check(limited).can_add_uses,
        check(limited).can_extend,
        check(limited).uses_left,
    ) == (True, False, 5)
    assert (
        check(dated).can_add_uses,
        check(dated).can_extend,
        check(dated).uses_left,
    ) == (False, True, None)
    assert check(voided).reason == "already_voided"


def test_the_redeem_check_says_why_a_session_cannot_be_spent(tax):
    cut, shampoo = make_service("Cut", tax=tax), make_service("Shampoo", tax=tax)
    package = make_package("Bono", [cut], max_uses=1, validity_days=30)
    fresh = make_grant(package, make_customer("A"))
    spent = make_grant(package, make_customer("B"))
    make_redemption(spent, cut)
    expired = make_grant(package, make_customer("C"), days_ago=31)
    voided = make_grant(package, make_customer("D"), voided_at=timezone.now())
    check = lambda grant, **service: run(
        "service.grant.redeem_check", RedeemCheckIn(id=grant.id, **service)
    )  # noqa: E731
    assert (check(fresh).redeemable, check(fresh).reason, check(fresh).remaining) == (
        True,
        "",
        1,
    )
    assert check(fresh, service="Shampoo").reason == "does_not_cover_service"
    assert check(fresh, service_id=cut.id).redeemable is True
    assert check(spent).reason == "no_uses_left"
    assert check(expired).reason == "expired"
    assert check(voided).reason == "voided"
    assert shampoo.id


# ── Sessions of the till (SERVICE-F22–F27) ───────────────────────────────────────────────────

def test_a_voucher_whose_only_hold_expired_can_be_voided_again(tax):
    cut = make_service("Cut", tax=tax)
    grant = make_grant(make_package("Bono", [cut], max_uses=1), make_customer())
    make_redemption(
        grant,
        cut,
        status="held",
        hold_until=timezone.now() - dt.timedelta(seconds=1),
        order_line_id=uuid.uuid7(),
    )
    check = run("service.grant.void_check", ByIdIn(id=grant.id))
    assert (check.voidable, check.used) == (True, 0)
