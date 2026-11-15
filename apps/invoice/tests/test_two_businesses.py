"""Invoicing runs as production does: each business in its own database and inside its own context.

Every test of the app runs inside ``hub_a``'s context (``conftest.py``); these check that it is so, and that an invoice
of ``hub_b`` is numbered and kept in ``hub_b``'s database alone, never in ``hub_a``'s.
"""

import pytest

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import B, IN_HUBS, ISSUER, ctx_for, run
from base.tenancy import context
from base.tenancy.context import HubContextMismatch, use_hub
from base.tenancy.tests import hubs

pytestmark = IN_HUBS

LINE = {"description": "Haircut course", "quantity": "1", "unit_price": 5000, "tax_rate": "21"}
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, 28004 Madrid",
}


def invoice(ctx=None):
    return run("invoice.invoice.create", {"lines": [LINE], **RECIPIENT}, ctx)


def test_a_test_of_invoicing_runs_in_hub_as_own_database_with_no_fallback():
    assert context._test_fallback is None
    assert context.current_alias() == hubs.HUB_A_ALIAS


def test_each_business_numbers_its_invoices_in_its_own_database(issuer, hub_b):
    ours = invoice()
    with use_hub(hub_b), hubs.assert_only_alias(hubs.HUB_B_ALIAS):
        run("invoice.issuer.update", ISSUER, ctx_for(scope=B))
        theirs = invoice(ctx_for(scope=B))
        assert list(Invoice.objects.values_list("id", "sequence")) == [(theirs.id, 1)]
        assert InvoiceSeries.objects.get().current_number == 1

    assert (ours.sequence, theirs.sequence) == (1, 1)
    assert list(Invoice.objects.values_list("id", flat=True)) == [ours.id]
    assert InvoiceSeries.objects.get().current_number == 1


def test_an_invoice_of_hub_b_run_inside_hub_as_context_is_refused_and_written_nowhere(issuer, hub_b):
    with use_hub(hub_b):
        run("invoice.issuer.update", ISSUER, ctx_for(scope=B))

    with pytest.raises(HubContextMismatch):
        invoice(ctx_for(scope=B))

    assert not Invoice.objects.exists()
    with use_hub(hub_b):
        assert not Invoice.objects.exists()
        assert not InvoiceSeries.objects.filter(current_number__gt=0).exists()
