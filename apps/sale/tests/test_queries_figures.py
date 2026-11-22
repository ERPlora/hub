"""«Only mine or all» in the sales figures (SALE-F28): the period's figures, today's sales and tickets (the Home's
panels), the last seven days and what each professional sold add up every sale of the business only for whoever sees
everyone's sales and the business totals (``sale.view_all_sales`` and ``base.view_business_totals``: the owner, the
administrator and the manager). Anyone else who reads the sales gets the figures of their own sales, the ones their
sales list gives them, as Square's «view own sales reports» and Toast's «My reports»: Ana and Bea are employees of the
basic role, with nothing granted.

Over HTTP, as the screens, the Home's panels, the assistant and the API ask.
"""

import json
from uuid import uuid7

import pytest
from django.apps import apps
from live.context import system_context

from apps.sale.tests.conftest import HOST, HUB_DB, A, ctx_for, run

pytestmark = HUB_DB

CARD = [{"method": "card"}]
#: The professional who served the coffees of both employees' sales.
CARLA = uuid7()
#: What the voucher sessions done outside the till are worth: Carla's, and the one Ana did herself.
CARLAS_SESSION, ANAS_SESSION = 400, 500


def get(client, path, **params):
    response = client.get(f"/api{path}", params, HTTP_HOST=HOST)
    assert response.status_code == 200, response.content
    return response.json()


def post(client, path, data):
    response = client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=HOST)
    assert response.status_code in (200, 201), response.content
    return response.json()


def grant(monkeypatch, app: str, role: str, *, add=(), drop=()):
    """``role`` with ``add`` and without ``drop`` in ``app``'s permissions, as a business's own role could have."""
    config = apps.get_app_config(app)
    granted = [p for p in config.role_permissions[role] if p not in drop] + list(add)
    monkeypatch.setattr(config, "role_permissions", {**config.role_permissions, role: granted})


@pytest.fixture
def anas_record(product, people):
    """Ana's staff record, on a day when Ana charges a coffee Carla served; Bea, one Carla served and one of her own,
    and the manager gives Carla's back. Outside the till, Carla did a voucher session, and Ana another one."""
    product("Coffee", "COF", 150, "restaurant.drink")
    ana, bea, marta = (people[name][1] for name in ("ana", "bea", "marta"))
    served = {"product": "COF", "staff_id": str(CARLA)}
    post(ana, "/sale/sales", {"idempotency_key": "figures-ana-0001", "lines": [served], "payments": CARD})
    theirs = post(
        bea,
        "/sale/sales",
        {"idempotency_key": "figures-bea-0001", "lines": [served, {"product": "COF"}], "payments": CARD},
    )
    carlas = next(line for line in theirs["lines"] if line["staff_id"] == str(CARLA))
    back = {
        "sale_id": theirs["id"],
        "reason": "Cold",
        "allocations": [{"payment_id": theirs["payments"][0]["id"], "amount": 150}],
        "lines": [{"line_id": carlas["id"], "quantity": "1"}],
    }
    post(marta, "/sale/sales/refund", back)
    record = run(
        "staff.member.create",
        {"first_name": "Ana", "last_name": "Ruiz", "user_id": str(people["ana"][0].person.pk)},
        system_context(A),
    )
    for staff_id, value in ((CARLA, CARLAS_SESSION), (record.id, ANAS_SESSION)):
        run("sale.voucher_session.record", {"session_id": str(uuid7()), "staff_id": str(staff_id), "value": value})
    return record.id


def period(client) -> tuple[int, int, int]:
    """Tickets, revenue and refunds of the period, as the Sales screen's figures say them."""
    stats = get(client, "/sale/sales/stats")
    return stats["count"], stats["total_revenue"], stats["refunded_total"]


def by_staff(client) -> list[tuple]:
    """Who, their tickets, gross, given back, revenue and production, as the close by professional says them."""
    return [
        (
            row["staff_id"],
            row["sales_count"],
            row["gross_total"],
            row["refunded_total"],
            row["total_revenue"],
            row["production_total"],
        )
        for row in get(client, "/sale/sales/by_staff")["rows"]
    ]


class TestAnEmployeeCountsOnlyHerOwnSales:
    def test_the_periods_figures_are_of_her_sales(self, people, anas_record):
        assert period(people["ana"][1]) == (1, 150, 0)
        assert period(people["bea"][1]) == (1, 150, 150)

    def test_today_and_the_last_seven_days_too(self, people, anas_record):
        ana = people["ana"][1]
        today = get(ana, "/sale/sales/today")
        assert (today["total"], today["tickets"]) == (150, 1)
        assert get(ana, "/sale/sales/last_7_days")["rows"][-1]["total"] == 150

    def test_the_close_by_professional_has_her_sales_lines_and_her_own_sessions(self, people, anas_record):
        # Carla only with the coffee of Ana's sale: Bea's sale, its refund and Carla's session are not Ana's.
        assert by_staff(people["ana"][1]) == [
            (str(anas_record), 0, 0, 0, 0, ANAS_SESSION),
            (str(CARLA), 1, 150, 0, 150, 150),
        ]

    def test_also_with_the_business_totals_she_counts_only_hers(self, monkeypatch, people, anas_record):
        grant(monkeypatch, "base", "hub_employee", add=["base.view_business_totals"])
        ana = people["ana"][1]
        assert period(ana) == (1, 150, 0)
        # Nor do the totals open the sessions other professionals did outside the till.
        assert by_staff(ana) == [
            (str(anas_record), 0, 0, 0, 0, ANAS_SESSION),
            (str(CARLA), 1, 150, 0, 150, 150),
        ]

    def test_the_home_panels_she_is_offered_read_only_her_sales(self, people, anas_record):
        ana = people["ana"][1]
        panels = {panel["key"]: panel for panel in get(ana, "/home/widgets")["widgets"] if panel["app"] == "sale"}
        assert panels["sale.today"]["operation"] == panels["sale.tickets_today"]["operation"] == "sale.sale.today"
        assert panels["sale.last_7_days"]["operation"] == "sale.sale.last_7_days"
        today = get(ana, "/sale/sales/today")
        assert (today["total"], today["tickets"]) == (150, 1)


class TestWhoCountsTheWholeBusiness:
    def test_the_manager_counts_every_sale_every_line_and_every_session(self, people, anas_record):
        marta = people["marta"][1]
        assert period(marta) == (2, 300, 150)
        today = get(marta, "/sale/sales/today")
        assert (today["total"], today["tickets"]) == (300, 2)
        assert get(marta, "/sale/sales/last_7_days")["rows"][-1]["total"] == 300
        assert by_staff(marta) == [
            (str(CARLA), 2, 300, 150, 150, 150 + CARLAS_SESSION),
            (str(anas_record), 0, 0, 0, 0, ANAS_SESSION),
        ]

    def test_seeing_everyones_sales_without_the_business_totals_counts_only_her_own(self, monkeypatch, people, anas_record):
        grant(monkeypatch, "base", "hub_manager", drop=["base.view_business_totals"])
        marta = people["marta"][1]
        # She still opens every sale one by one; her own figures are of the sales she charged: none.
        assert get(marta, "/sale/sales")["total"] == 2
        assert period(marta) == (0, 0, 0)
        today = get(marta, "/sale/sales/today")
        assert (today["total"], today["tickets"]) == (0, 0)
        assert get(marta, "/sale/sales/last_7_days")["rows"][-1]["total"] == 0
        assert by_staff(marta) == []

    def test_a_caller_that_is_not_a_person_counts_what_its_permission_opens(self, anas_record):
        # An API key or an automation has no sales of its own: reading the sales opens the business's.
        ctx = ctx_for("hub_employee", actor="flow:7")
        assert run("sale.sale.stats", {}, ctx).count == 2
