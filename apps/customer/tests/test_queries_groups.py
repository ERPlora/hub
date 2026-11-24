"""The customer group list (CUSTOMER-F27, ``groups_customer_count.pg``): how many live cards each group has, its
filters and its order."""

from apps.customer.models import CustomerGroup
from apps.customer.schemas.groups import GroupListIn

from .conftest import HUB_DB, NOW, card, run


pytestmark = HUB_DB


def test_the_group_list_counts_the_live_customers_of_each_group():
    vip, wholesale = (
        CustomerGroup.objects.create(name="VIP", sort_order=2),
        CustomerGroup.objects.create(name="Wholesale"),
    )
    for name in ("Ana", "Bea"):
        card(name).groups.add(vip, wholesale)
    card("Gone", deleted_at=NOW).groups.add(vip)
    CustomerGroup.objects.create(name="Old", is_active=False)
    page = run("customer.group.list", GroupListIn())
    assert [(row.name, row.customer_count, row.is_active) for row in page.rows] == [
        ("Old", 0, False),
        ("VIP", 2, True),
        ("Wholesale", 2, True),
    ]
    assert [
        row.name
        for row in run(
            "customer.group.list",
            GroupListIn(is_active=True, sort="sort_order", descending=True),
        ).rows
    ] == [
        "VIP",
        "Wholesale",
    ]
    assert [
        row.name for row in run("customer.group.list", GroupListIn(search="whole")).rows
    ] == ["Wholesale"]
    assert [
        row.name
        for row in run(
            "customer.group.list", GroupListIn(customers_min=1, sort="customer_count")
        ).rows
    ] == [
        "VIP",
        "Wholesale",
    ]
