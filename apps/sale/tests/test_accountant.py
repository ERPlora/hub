"""The accountancy firm (``hub_accountant``, «Gestoría») in Sales: it reads everyone's sales, how they were paid and
the whole business's figures; it never opens a check, charges nor changes the till's settings.

Over HTTP, as the screens, the assistant and the API ask, with two employees who charge and the firm that reads.
"""

import pytest
from django.test import Client

from apps.sale.queries.ownership import SALES
from apps.sale.tests.conftest import HUB_DB, ctx_for
from apps.sale.tests.test_queries_ownership import coffee, get, listed, post, sales

__all__ = ["coffee", "sales"]

pytestmark = HUB_DB

REFUSED = "permission_denied"


@pytest.fixture
def gema(make_user):
    """Gema, of the business's accountancy firm, signed in on her own computer."""
    user = make_user("gema", role="hub_accountant")
    client = Client()
    client.force_login(user)
    return user, client


def test_it_lists_and_opens_the_sales_of_everyone(gema, sales):
    _, client = gema

    assert listed(client) == {sale["number"] for sale in sales.values()}
    for sale in sales.values():
        detail = get(client, "/sale/sales/detail", sale_id=sale["id"])
        assert detail.status_code == 200, detail.content
        assert detail.json()["total"] == sale["total"]


def test_it_reads_how_they_were_paid(gema, sales):
    response = get(gema[1], "/sale/payment_methods")

    assert response.status_code == 200, response.content
    assert "card" in {method["type"] for method in response.json()["rows"]}


def test_its_figures_add_up_the_whole_business(gema, sales):
    user, _ = gema

    counted = SALES.counted(ctx_for("hub_accountant", actor=user))

    assert {str(pk) for pk in counted.values_list("id", flat=True)} == {sale["id"] for sale in sales.values()}


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/sale/orders", {}),
        ("/sale/sales", {"idempotency_key": "gema-0001", "lines": [{"product": "COF"}], "payments": [{"method": "card"}]}),
        ("/sale/settings", {"allow_discounts": False}),
    ],
    ids=["open-a-check", "charge", "change-the-settings"],
)
def test_it_neither_sells_charges_nor_changes_the_settings(gema, coffee, path, body):
    response = post(gema[1], path, body)

    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == REFUSED
