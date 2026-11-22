"""An API key never does more than whoever made it (BASE-F125).

A key remembers its maker (``ApiKey.owner``, a ``HubUser`` of the business) and, at the door, holds only what its maker
holds on the business today: the operation's permission, the data permissions and the «see everyone's» ones, each only
if the maker has it; for what has an owner, it reads as its maker. A maker no longer in the business leaves the key
opening nothing (403 ``base.api_key_owner_gone``). A key made before its maker was recorded goes to the business's owner
with the next photo from erplora.com; until then it does what it did, as the owner's.
"""

import datetime as dt
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError

from apps.sale.models import Sale
from apps.tax.models import TaxCategory
from base.models import HubUser, Membership
from base.models.api_keys import ApiKey
from base.services import hub_registry
from base.tenancy.context import use_hub
from base.tests.test_api_keys import HUB_DB, bearer, code, create, get, host, member, post
from base.tests.test_hub_users import SYSTEM, photo

pytestmark = HUB_DB

MAKER = "saas:1"
CONFIG = "/inventory/config"
PRODUCTS = "/inventory/products"
SALES = "/sale/sales"
CARTS = "/cart_checkout/carts"


@pytest.fixture
def made(client, hub_a):
    """A full key made by an administrator of business A, and the client, signed out, that calls with it."""
    client.force_login(member(hub_a.slug, username=MAKER))
    token = create(client, hub_a)["token"]
    client.logout()
    return bearer(token)


def maker_becomes(hub, role: str) -> None:
    Membership.objects.filter(user__username=MAKER, host=hub.slug).update(role=role)


def a_product_costing_90(client, hub, key) -> None:
    with use_hub(hub):
        TaxCategory.objects.get_or_create(key="test.general", defaults={"name": "General"})
    tea = {"name": "Tea", "sku": "TEA", "price": 150, "cost": 90, "tax_category_key": "test.general"}
    assert post(client, host(hub), PRODUCTS, tea, **key).status_code == 201


def costs(client, hub, key) -> list:
    response = get(client, host(hub), PRODUCTS, **key)
    assert response.status_code == 200, response.content
    return [row["cost"] for row in response.json()["rows"]]


def sales_charged_by(hub, *people: str) -> None:
    with use_hub(hub):
        for number, who in enumerate(people, start=1):
            Sale.objects.create(
                number=f"20261122-{number:04d}",
                business_day=dt.date(2026, 11, 22),
                sequence=number,
                idempotency_key=f"key-{number}",
                total=100,
                subtotal=91,
                tax_total=9,
                created_by=who,
            )


def charged_by(client, hub, key) -> list[str]:
    response = get(client, host(hub), SALES, **key)
    assert response.status_code == 200, response.content
    return sorted(row["number"] for row in response.json()["rows"])


class TestTheMaker:
    def test_a_new_key_records_whoever_made_it(self, made, hub_a):
        with use_hub(hub_a):
            assert ApiKey.objects.get().owner.username == MAKER

    def test_the_photo_gives_the_keys_made_before_to_the_owner_and_keeps_the_others(self, client, hub_a):
        olga, admin = uuid.UUID("0199c4b0-0000-7000-8000-00000000b0b0"), uuid.UUID("0199c4b0-0000-7000-8000-0000000000a1")
        client.force_login(member(hub_a.slug, username=f"saas:{admin}"))
        create(client, hub_a, name="Shop")
        create(client, hub_a, name="Accountant")
        with use_hub(hub_a):
            ApiKey.objects.filter(name="Accountant").update(owner=None)

        hub_registry.hub_state_apply(
            SYSTEM,
            photo(1, (admin, "Ana", "", "hub_admin"), (olga, "Olga", "", "hub_owner"), hub_id=hub_a.id, slug=hub_a.slug),
        )

        with use_hub(hub_a):
            owners = dict(ApiKey.objects.values_list("name", "owner__username"))
        assert owners == {"Shop": f"saas:{admin}", "Accountant": f"saas:{olga}"}


class TestTheCeiling:
    def test_a_key_loses_a_permission_its_maker_loses(self, made, client, hub_a):
        assert get(client, host(hub_a), CONFIG, **made).status_code == 200

        maker_becomes(hub_a, Membership.Role.EMPLOYEE)

        refused = get(client, host(hub_a), CONFIG, **made)
        assert (refused.status_code, code(refused)) == (403, "permission_denied")

    def test_a_key_of_a_maker_without_view_costs_gets_the_cost_empty(self, made, client, hub_a):
        a_product_costing_90(client, hub_a, made)
        assert costs(client, hub_a, made) == [90]

        maker_becomes(hub_a, Membership.Role.EMPLOYEE)

        assert costs(client, hub_a, made) == [None]

    def test_a_key_of_a_maker_without_every_sale_reads_only_the_maker_s(self, made, client, hub_a):
        sales_charged_by(hub_a, MAKER, "saas:2")
        assert charged_by(client, hub_a, made) == ["20261122-0001", "20261122-0002"]

        maker_becomes(hub_a, Membership.Role.EMPLOYEE)

        assert charged_by(client, hub_a, made) == ["20261122-0001"]


class TestAMakerWhoLeft:
    @pytest.mark.parametrize(
        "leave",
        [
            lambda hub: Membership.objects.filter(user__username=MAKER, host=hub.slug).delete(),
            lambda hub: get_user_model().objects.filter(username=MAKER).update(is_active=False),
        ],
        ids=["out of the business", "account closed"],
    )
    def test_the_key_opens_nothing_and_says_so(self, made, client, hub_a, leave):
        leave(hub_a)

        refused = get(client, host(hub_a), CARTS, **made)

        assert (refused.status_code, code(refused)) == (403, "base.api_key_owner_gone")
        with use_hub(hub_a):
            assert ApiKey.objects.get().last_used_at is None

    def test_a_key_made_before_its_maker_was_recorded_does_what_it_did(self, made, client, hub_a):
        a_product_costing_90(client, hub_a, made)
        with use_hub(hub_a):
            ApiKey.objects.update(owner=None)
        Membership.objects.filter(user__username=MAKER, host=hub_a.slug).delete()

        assert costs(client, hub_a, made) == [90]

    def test_a_maker_is_never_deleted_while_a_key_names_them(self, made, hub_a):
        with use_hub(hub_a), pytest.raises(ProtectedError):
            HubUser.objects.filter(username=MAKER).delete()
