"""A quantity typed on a line that does not fit the step of its unit (SALE-F10): refused over HTTP with the reason
and the step in the reader's language, however many decimals it has, and the line keeps its quantity."""

import pytest

from apps.sale.tests.conftest import HUB_DB
from apps.sale.tests.test_api import get, post

pytestmark = HUB_DB


@pytest.fixture
def cashier(client, make_user):
    client.force_login(make_user("ana", role="hub_employee"))
    return client


@pytest.fixture
def prawns_line(cashier, product):
    product("Prawns", "PRW", 2400, "restaurant.food", unit="kg")
    check = post(
        cashier,
        "/sale/orders",
        {"label": "Bar", "lines": [{"product": "PRW", "quantity": "0.532"}]},
    ).json()
    return check["id"], check["lines"][0]["id"]


def test_a_weight_finer_than_a_gram_is_refused_with_the_step_and_the_line_stays(
    cashier, prawns_line
):
    order_id, line_id = prawns_line
    finer = {"order_id": order_id, "line_id": line_id, "quantity": "1.2505"}
    english = post(cashier, "/sale/orders/update_line", finer)
    spanish = post(
        cashier, "/sale/orders/update_line", finer, HTTP_ACCEPT_LANGUAGE="es"
    )
    assert (english.status_code, english.json()["error"]["code"]) == (
        409,
        "sale.quantity_off_grid",
    )
    assert (
        english.json()["error"]["message"]
        == "The quantity does not fit the step of the product (0.001 kg)."
    )
    assert (
        spanish.json()["error"]["message"]
        == "La cantidad no encaja con el escalón del producto (0,001 kg)."
    )
    check = get(cashier, "/sale/orders/detail", order_id=order_id).json()
    assert check["lines"][0]["quantity"] == "0.532"


def test_a_weight_on_the_step_is_kept(cashier, prawns_line):
    order_id, line_id = prawns_line
    kept = post(
        cashier,
        "/sale/orders/update_line",
        {"order_id": order_id, "line_id": line_id, "quantity": "1.250"},
    )
    assert kept.status_code == 200
    assert kept.json()["lines"][0]["quantity"] == "1.250"


def test_a_quantity_too_big_to_keep_is_refused_before_the_line(cashier, prawns_line):
    order_id, line_id = prawns_line
    huge = post(
        cashier,
        "/sale/orders/update_line",
        {"order_id": order_id, "line_id": line_id, "quantity": "1000000000000"},
    )
    assert (huge.status_code, huge.json()["error"]["code"]) == (422, "invalid_payload")
    check = get(cashier, "/sale/orders/detail", order_id=order_id).json()
    assert check["lines"][0]["quantity"] == "0.532"


@pytest.mark.parametrize("typed", ["1E-1000030", "0.0005", "1E-30"])
def test_a_quantity_smaller_than_any_step_is_refused_and_the_line_stays(
    cashier, prawns_line, typed
):
    order_id, line_id = prawns_line
    tiny = post(
        cashier,
        "/sale/orders/update_line",
        {"order_id": order_id, "line_id": line_id, "quantity": typed},
    )
    assert (tiny.status_code, tiny.json()["error"]["code"]) == (
        409,
        "sale.quantity_off_grid",
    )
    check = get(cashier, "/sale/orders/detail", order_id=order_id).json()
    assert check["lines"][0]["quantity"] == "0.532"
