"""Django admin of the invoice app, for the platform's staff (hubs.erplora.com, PLAN §17–§18).

Series and issuer: full CRUD, ids and dates read-only. Invoices and their lines: every field is shown and
the fiscal ones are read-only; there is no adding (the number comes only from the operations) and no
deleting (the law keeps an issued invoice: RD 1619/2012 art. 19); only the notes can be changed.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from apps.invoice.admin import (
    InvoiceAdmin,
    InvoiceLineInline,
    InvoiceSeriesAdmin,
    IssuerAdmin,
)
from apps.invoice.models import Invoice, InvoiceSeries, Issuer
from apps.invoice.tests.conftest import run

FISCAL = {
    "invoice_type",
    "series",
    "series_code",
    "year",
    "sequence",
    "number",
    "issue_date",
    "operation_date",
    "issued_at",
    "issuer_name",
    "issuer_tax_id",
    "issuer_address",
    "issuer_country",
    "customer",
    "customer_name",
    "customer_tax_id",
    "customer_address",
    "customer_country",
    "customer_id_type",
    "description",
    "base_amount",
    "tax_amount",
    "total_amount",
    "tax_breakdown",
    "currency",
    "source_type",
    "source_sale",
    "source_refund",
    "rectifies",
    "substitutes",
    "rectification_kind",
    "status",
    "paid_at",
    "created_by",
}


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_the_four_models_are_registered():
    assert isinstance(admin.site._registry[InvoiceSeries], InvoiceSeriesAdmin)
    assert isinstance(admin.site._registry[Issuer], IssuerAdmin)
    assert isinstance(admin.site._registry[Invoice], InvoiceAdmin)
    assert admin.site._registry[Invoice].inlines == [InvoiceLineInline]


def test_series_and_issuer_have_full_crud(superuser):
    request = request_by(superuser)
    for model in (InvoiceSeries, Issuer):
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request)
        assert model_admin.has_add_permission(request)
        assert model_admin.has_change_permission(request)
        assert model_admin.has_delete_permission(request)
        assert {"id", "updated_at"} <= set(model_admin.get_readonly_fields(request))


def test_an_issued_invoice_is_read_with_its_fiscal_fields_read_only_and_never_deleted(
    superuser,
):
    request = request_by(superuser)
    invoices = admin.site._registry[Invoice]
    assert invoices.has_view_permission(request)
    assert not invoices.has_add_permission(request)
    assert not invoices.has_delete_permission(request)
    assert FISCAL | {"id", "updated_at"} <= set(invoices.get_readonly_fields(request))
    assert "notes" not in invoices.get_readonly_fields(request)
    lines = InvoiceLineInline(Invoice, admin.site)
    assert not lines.has_add_permission(request, None)
    assert not lines.has_delete_permission(request)
    assert set(lines.get_readonly_fields(request)) >= {
        "description",
        "quantity",
        "unit_price",
        "base_amount",
        "tax_amount",
        "total_amount",
    }


@pytest.mark.django_db
def test_the_pages_render(client, superuser, issuer):
    invoice = run(
        "invoice.invoice.create",
        {
            "lines": [
                {
                    "description": "Hair course",
                    "quantity": "1",
                    "unit_price": 1000,
                    "tax_rate": "21",
                }
            ],
            "customer_name": "Talleres Pérez SL",
            "customer_tax_id": "B12345674",
            "customer_address": "Calle Luna 3",
        },
    )
    series = InvoiceSeries.objects.get(code="FACT")
    client.force_login(superuser)
    pages = {
        "/admin/invoice/invoice/": invoice.number.encode(),
        f"/admin/invoice/invoice/{invoice.id}/change/": b"Hair course",
        "/admin/invoice/invoiceseries/": b"FACT",
        f"/admin/invoice/invoiceseries/{series.pk}/change/": b"FACT",
        "/admin/invoice/invoiceseries/add/": b"code",
        "/admin/invoice/issuer/": b"B12345674",
        f"/admin/invoice/issuer/{Issuer.objects.get().pk}/change/": b"Calle Mayor 1",
    }
    for path, content in pages.items():
        response = client.get(path, HTTP_HOST="hubs.localhost")
        assert response.status_code == 200, path
        assert content in response.content, path


@pytest.mark.django_db
def test_the_staff_can_change_the_notes_of_an_invoice_and_nothing_fiscal(
    client, superuser, issuer
):
    invoice = run(
        "invoice.invoice.create",
        {
            "series_code": "TICKET",
            "lines": [
                {
                    "description": "Coffee",
                    "quantity": "1",
                    "unit_price": 150,
                    "tax_rate": "10",
                }
            ],
        },
    )
    client.force_login(superuser)
    response = client.post(
        f"/admin/invoice/invoice/{invoice.id}/change/",
        {
            "notes": "Checked by support",
            "total_amount": "1",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "1",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-id": str(invoice.lines[0].id),
            "lines-0-invoice": str(invoice.id),
        },
        HTTP_HOST="hubs.localhost",
    )
    assert response.status_code == 302, response.content[:2000]
    stored = Invoice.objects.get(pk=invoice.id)
    assert (stored.notes, stored.total_amount) == ("Checked by support", 165)


@pytest.mark.django_db
def test_a_series_keeps_its_identity_and_freezes_its_numbering_once_it_numbers(
    superuser, issuer
):
    request = request_by(superuser)
    series_admin = admin.site._registry[InvoiceSeries]
    identity = {"code", "year", "invoice_type"}
    numbering = {"prefix", "format", "current_number"}
    assert not (identity | numbering) & set(series_admin.get_readonly_fields(request))
    shop = InvoiceSeries.objects.get(
        pk=run(
            "invoice.series.create",
            {
                "code": "SHOP",
                "invoice_type": "F1",
                "year": timezone.localdate().year,
                "next_number": 7,
            },
        ).id
    )
    fresh = set(series_admin.get_readonly_fields(request, shop))
    assert identity <= fresh and not numbering & fresh
    run(
        "invoice.invoice.create",
        {
            "series_code": "SHOP",
            "lines": [{"description": "x", "quantity": "1", "unit_price": 100, "tax_rate": "21"}],
            "customer_name": "Talleres Pérez SL",
            "customer_tax_id": "B12345674",
            "customer_address": "Calle Luna 3",
        },
    )
    shop.refresh_from_db()
    assert identity | numbering <= set(series_admin.get_readonly_fields(request, shop))


@pytest.mark.django_db
def test_the_issuer_form_checks_the_tax_id(client, superuser):
    client.force_login(superuser)
    form = {
        "legal_name": "Peluquería Ana SL",
        "tax_id": "B12345675",
        "address": "Calle Mayor 1",
        "postal_code": "28001",
        "city": "Madrid",
        "province": "Madrid",
        "country": "ES",
        "source": "manual",
        "singleton": "on",
    }
    refused = client.post("/admin/invoice/issuer/add/", form, HTTP_HOST="hubs.localhost")
    assert refused.status_code == 200 and b"tax ID is not valid" in refused.content
    assert not Issuer.objects.exists()
    saved = client.post(
        "/admin/invoice/issuer/add/",
        {**form, "tax_id": "b-12345674"},
        HTTP_HOST="hubs.localhost",
    )
    assert saved.status_code == 302, saved.content[:2000]
    assert Issuer.objects.get().tax_id == "B12345674"
