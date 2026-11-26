"""Who voided, adjusted or spent a voucher never shows a colleague's email (BASE-F119, SERVICE-F17, SERVICE-F19).

A colleague whose account has no name of its own is named by the part before the «@» in the sold vouchers and in a
voucher's movements, and that is what is kept: an employee who sees no colleague's contact details reads it there.
What was saved with an address before is cleaned once by the app's migration (``test_migrations``).
"""

import pytest
from live.context import system_context
from live.operations import get as operation

from apps.flow.tests.test_api import get, post
from apps.service.models.grants import Grant, GrantAdjustment, Redemption
from base.tests.colleagues import ADDRESS, NAMELESS, SHOWN, signed_in

from .conftest import HUB_DB, A

pytestmark = HUB_DB


def by_the_platform(name: str, data: dict):
    op = operation(name)
    return op(system_context(A), op.input.model_validate(data))


def two_vouchers() -> tuple[str, str, str]:
    """Two «Five cuts» sold to Lucía: the package's id and the two vouchers' ids."""
    cut = by_the_platform("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"})
    package = by_the_platform("service.package.create", {"name": "Five cuts", "max_uses": 5, "items": [{"service_id": str(cut.id), "sessions": 5}]})
    lucia = by_the_platform("customer.customer.create", {"name": "Lucía Gómez"})
    sold = [by_the_platform("service.grant.create", {"package_id": str(package.id), "customer_id": str(lucia.id)}) for _ in "ab"]
    return str(package.id), str(sold[0].id), str(sold[1].id)


@pytest.mark.parametrize("account", NAMELESS.values(), ids=NAMELESS)
def test_a_colleague_without_a_name_who_voids_adjusts_or_spends_a_voucher_is_named_without_their_address(account):
    package, voided, used = two_vouchers()
    zoe = signed_in("zoe", "hub_manager", **account)
    writes = [
        post(zoe, "/service/grants/void", {"id": voided, "reason": "Sold by mistake"}),
        post(zoe, "/service/grants/adjust", {"id": used, "uses_delta": 1, "reason": "A gift"}),
        post(zoe, "/service/grants/redeem", {"id": used, "service": "Haircut"}),
    ]
    assert [answer.status_code for answer in writes] == [200, 200, 200], [answer.content for answer in writes]
    ana = signed_in("ana")

    sold = get(ana, "/service/grants")
    movements = get(ana, "/service/movements", package_id=package)

    assert (sold.status_code, movements.status_code) == (200, 200)
    assert ADDRESS not in sold.content.decode() + movements.content.decode()
    assert [row["voided_by"] for row in sold.json()["rows"] if row["id"] == voided] == [SHOWN]
    assert [row["actor"] for row in movements.json()["rows"]] == [SHOWN, SHOWN]
    assert Grant.objects.get(pk=voided).voided_by == SHOWN
    assert GrantAdjustment.objects.get(grant_id=used).actor == Redemption.objects.get(grant_id=used).actor == SHOWN
