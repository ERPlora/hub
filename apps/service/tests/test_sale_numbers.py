"""The list of the vouchers sold says the sale that charged each one by the number Sales names it by (SERVICE-F16),
read from Sales as whoever looks reads it, with Sales' real operations: nothing of the sale is copied into Services."""

import dataclasses

import pytest
from live.errors import AppInactive
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get, registry

from apps.sale.tests.conftest import charged_open, grant_for, run, svc
from base.operations import call

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB


@pytest.fixture
def haircut(db):
    return svc("service.service.create", {"name": "Haircut", "price": 2500, "tax_category_key": "service.generic"})


@pytest.fixture
def lucia(db):
    return run("customer.customer.create", {"name": "Lucía Pérez"})


def sold_list(grant, ctx=None):
    op = get("service.grant.list")
    return op(ctx or ctx_for("hub_admin"), op.input.model_validate({"package_id": str(grant.package_id)})).rows


def said_of_the_sale(row) -> tuple:
    return (row.sale_id, row.sale_number)


def voucher_of(sale, lucia, haircut):
    return grant_for(lucia, haircut, sale_id=str(sale.id))


def test_a_voucher_sold_with_its_sale_says_it_by_its_number(haircut, lucia):
    sale = charged_open("num-00001", ("Bono de 100", 10000, None))
    [row] = sold_list(voucher_of(sale, lucia, haircut))
    assert said_of_the_sale(row) == (sale.id, sale.number)


def test_a_voucher_granted_without_its_sale_says_no_sale(haircut, lucia):
    [row] = sold_list(grant_for(lucia, haircut))
    assert said_of_the_sale(row) == (None, None)


def test_whoever_may_not_see_sales_reads_the_voucher_without_its_sale(haircut, lucia):
    sale = charged_open("num-00002", ("Bono de 100", 10000, None))
    allowed = permissions_for_role(all_live_app_configs(), "hub_admin") - {"sale.view_sale"}
    [row] = sold_list(voucher_of(sale, lucia, haircut), ctx_for("hub_admin", permissions=allowed))
    assert said_of_the_sale(row) == (sale.id, None)


def test_an_employee_reads_without_its_number_a_sale_that_is_not_theirs(haircut, lucia, make_user):
    # Sales answers «does not exist» for a sale someone else charged, to whoever may only see theirs.
    sale = charged_open("num-00003", ("Bono de 100", 10000, None))
    grant = voucher_of(sale, lucia, haircut)
    ana = make_user("ana", role="hub_employee")
    [theirs] = sold_list(grant, ctx_for("hub_employee", actor=ana))
    [manager] = sold_list(grant, ctx_for("hub_admin", actor=ana))
    assert (said_of_the_sale(theirs), said_of_the_sale(manager)) == ((sale.id, None), (sale.id, sale.number))


def off(ctx, data):
    raise AppInactive("Off.")


@pytest.mark.parametrize("sales", ["absent", "off"])
def test_without_sales_the_list_still_reads_without_the_sale(haircut, lucia, monkeypatch, sales):
    sale = charged_open("num-00004", ("Bono de 100", 10000, None))
    grant = voucher_of(sale, lucia, haircut)
    if sales == "absent":
        for name in [name for name in registry if name.startswith("sale.")]:
            monkeypatch.delitem(registry, name)
    else:
        monkeypatch.setitem(registry, "sale.sale.get", dataclasses.replace(registry["sale.sale.get"], fn=off))
    [row] = sold_list(grant)
    assert said_of_the_sale(row) == (sale.id, None)


def test_each_sale_of_a_page_is_read_once(haircut, lucia, monkeypatch):
    # Two vouchers charged by the same sale (two lines of it) and one by another: two reads of Sales, not three.
    both = charged_open("num-00005", ("Bono de 100", 10000, None), ("Bono de 50", 5000, None))
    other = charged_open("num-00006", ("Bono de 100", 10000, None))
    package = svc("service.package.create", {"name": "Bono 3", "max_uses": 3, "items": [{"service_id": str(haircut.id)}]})
    for sale, line in ((both, both.lines[0]), (both, both.lines[1]), (other, other.lines[0])):
        svc(
            "service.grant.create",
            {
                "package_id": str(package.id),
                "customer_id": str(lucia.id),
                "amount": line.line_total,
                "sale_id": str(sale.id),
                "sale_line_id": str(line.id),
            },
        )
    asked = []

    def counted(ctx, name, data, **more):
        asked.append(data["sale_id"])
        return call(ctx, name, data, **more)

    monkeypatch.setattr("apps.service.queries.sale_numbers.call", counted)
    op = get("service.grant.list")
    rows = op(ctx_for("hub_admin"), op.input.model_validate({"package_id": str(package.id)})).rows
    assert sorted(row.sale_number for row in rows) == sorted([both.number, both.number, other.number])
    assert sorted(asked) == sorted([str(both.id), str(other.id)])


@pytest.mark.parametrize(
    "write", ["service.grant.create", "service.grant.void", "service.grant.adjust", "service.grant.link"]
)
def test_the_writes_of_a_voucher_answer_without_the_number_of_its_sale(write):
    # Only the list that shows it asks Sales: a write answers the voucher as it is in Services.
    listed = get("service.grant.list").output.model_fields["rows"].annotation.__args__[0]
    assert ("sale_number" in listed.model_fields, "sale_number" in get(write).output.model_fields) == (True, False)
