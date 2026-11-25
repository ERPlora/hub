"""The declarations of the customer app's read operations: their kind, permission, schemas and whether an API key
reaches them. What each one reads is tested beside its module, in ``test_queries_<module>.py``."""

import pytest
from live.operations import get

from apps.customer.schemas.activity import ActivityListIn, ActivityPage
from apps.customer.schemas.cards import (
    ByPhoneIn,
    CustomerDetailOut,
    CustomerListIn,
    CustomerPage,
    CustomerStatsIn,
    CustomerStatsOut,
    PhoneMatchOut,
)
from apps.customer.schemas.consent import ConsentHistoryIn, ConsentPage, ConsentStateIn, ConsentStateOut
from apps.customer.schemas.custom_fields import FieldListIn, FieldPage
from apps.customer.schemas.exports import CustomerExportIn, ExportOut
from apps.customer.schemas.fields import CustomerRefIn
from apps.customer.schemas.groups import GroupListIn, GroupPage
from apps.customer.schemas.orders import OrderCustomerOut, OrderIn, OrderListIn, OrderPage
from apps.customer.schemas.purchases import DivergencePage, DivergencesIn, PurchaseListIn, PurchasePage
from apps.customer.schemas.tags import TagListIn, TagPage

from .conftest import HUB_DB


pytestmark = HUB_DB


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "expose_api"),
    [
        (
            "customer.customer.list",
            "customer.view",
            CustomerListIn,
            CustomerPage,
            False,
        ),
        (
            "customer.customer.detail",
            "customer.view",
            CustomerRefIn,
            CustomerDetailOut,
            False,
        ),
        (
            "customer.customer.stats",
            "customer.view",
            CustomerStatsIn,
            CustomerStatsOut,
            False,
        ),
        (
            "customer.customer.by_phone",
            "customer.view",
            ByPhoneIn,
            PhoneMatchOut,
            False,
        ),
        (
            "customer.customer.export",
            "customer.export",
            CustomerExportIn,
            ExportOut,
            False,
        ),
        ("customer.group.list", "customer.view", GroupListIn, GroupPage, False),
        ("customer.tag.list", "customer.view", TagListIn, TagPage, False),
        ("customer.field.list", "customer.view", FieldListIn, FieldPage, False),
        (
            "customer.activity.list",
            "customer.view",
            ActivityListIn,
            ActivityPage,
            False,
        ),
        (
            "customer.purchase.list",
            "customer.view",
            PurchaseListIn,
            PurchasePage,
            False,
        ),
        (
            "customer.purchase.divergences",
            "customer.view",
            DivergencesIn,
            DivergencePage,
            False,
        ),
        (
            "customer.consent.state",
            "customer.view",
            ConsentStateIn,
            ConsentStateOut,
            True,
        ),
        (
            "customer.consent.history",
            "customer.view",
            ConsentHistoryIn,
            ConsentPage,
            False,
        ),
        ("customer.order.customer", "customer.view", OrderIn, OrderCustomerOut, False),
        ("customer.order.list", "customer.view", OrderListIn, OrderPage, True),
    ],
)
def test_declarations(name, permission, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "query",
        permission,
        input,
        output,
        expose_api,
    )
