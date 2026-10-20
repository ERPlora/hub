"""Django admin of the sale app, for the platform's staff only (hubs.erplora.com, PLAN §17–§18).

The open tables (payment methods, settings, departments, quick notes, open checks and their lines) keep
full CRUD. What was charged is a fiscal document (PLAN-HUB §3.2, round 2026-10-20): sales, their lines and
payments, the day's counter that numbers them, and refunds with their lines and payments are shown whole
and never added nor deleted; only the notes of a sale and of a refund can change. A charge is corrected by
its void or its refunds, as at the till. Ids and timestamps are shown, never typed.
"""

from html.parser import HTMLParser

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.sale import admin as sale_admin
from apps.sale.models import (
    Department,
    Order,
    OrderLine,
    PaymentMethod,
    QuickNote,
    Refund,
    RefundLine,
    RefundPayment,
    Sale,
    SaleCounter,
    SaleLine,
    SalePayment,
    Settings,
)
from apps.sale.tests.conftest import run

OPEN = [PaymentMethod, Settings, Department, QuickNote, Order, OrderLine]
CHARGED = [Sale, SaleLine, SalePayment, SaleCounter, Refund, RefundPayment, RefundLine]
MODELS = OPEN + CHARGED

HOST = {"HTTP_HOST": "hubs.localhost", "HTTP_ACCEPT_LANGUAGE": "en"}


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )


@pytest.fixture
def staff(client, superuser):
    """The platform staff, signed in to the Hub admin."""
    client.force_login(superuser)
    return client


def request_by(user):
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def charge(key: str, quantity: str = "1"):
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "lines": [{"product": "COF", "quantity": quantity}],
            "payments": [{"method": "cash", "amount": 150 * int(quantity)}],
        },
    )


@pytest.fixture
def charged(product):
    """A coffee charged and two more charged with one of them refunded: a row in every table of what was
    charged."""
    product()
    charge("admin-plain-0001")
    refunded = charge("admin-refunded-0001", quantity="2")
    run(
        "sale.sale.refund",
        {
            "sale_id": str(refunded.id),
            "reason": "returned",
            "allocations": [{"payment_id": str(refunded.payments[0].id), "amount": 150}],
            "lines": [{"line_id": str(refunded.lines[0].id), "quantity": "1"}],
        },
    )


def a_row(model):
    """A row of ``model`` that nothing protects: the sale without refunds, its line and its payment, or the
    only row of the other tables."""
    plain = Sale.objects.get(refunds__isnull=True)
    return {Sale: plain, SaleLine: plain.lines.get(), SalePayment: plain.payments.get()}.get(
        model
    ) or model.objects.get()


def url(row, view: str) -> str:
    meta = row._meta
    return f"/admin/{meta.app_label}/{meta.model_name}/{row.pk}/{view}/"


def changelist(model) -> str:
    return f"/admin/{model._meta.app_label}/{model._meta.model_name}/"


class BrowserForm(HTMLParser):
    """What a browser sends from the admin's change form (``id="<model>_form"``) as it is rendered."""

    def __init__(self, form_id: str):
        super().__init__()
        self.form_id = form_id
        self.inside = False
        self.data: dict[str, list[str]] = {}
        self.textarea: str | None = None
        self.select: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.inside = attrs.get("id") == self.form_id
            return
        name = attrs.get("name")
        if not self.inside:
            return
        if tag == "input" and name:
            kind = attrs.get("type", "text")
            if kind in ("checkbox", "radio"):
                if "checked" in attrs:
                    self.data.setdefault(name, []).append(attrs.get("value") or "on")
            elif kind not in ("submit", "button", "file", "image", "reset"):
                self.data.setdefault(name, []).append(attrs.get("value") or "")
        elif tag == "textarea" and name:
            self.textarea = name
            self.data.setdefault(name, []).append("")
        elif tag == "select" and name:
            self.select = name
        elif tag == "option" and self.select and "selected" in attrs:
            self.data.setdefault(self.select, []).append(attrs.get("value") or "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.inside = False
        elif tag == "textarea" and self.textarea:
            # A browser drops the newline that opens a textarea.
            value = self.data[self.textarea][-1]
            self.data[self.textarea][-1] = value.removeprefix("\n")
            self.textarea = None
        elif tag == "select":
            self.select = None

    def handle_data(self, data):
        if self.textarea:
            self.data[self.textarea][-1] += data


def save_change(client, row, **changes):
    """The admin's «Save» of ``row`` as a browser sends it, with ``changes`` typed over it."""
    page = client.get(url(row, "change"), **HOST)
    assert page.status_code == 200
    form = BrowserForm(f"{row._meta.model_name}_form")
    form.feed(page.content.decode())
    data = {**form.data, **{name: [value] for name, value in changes.items()}}
    return client.post(url(row, "change"), {**data, "_save": "Save"}, **HOST)


def fiscal(row) -> dict:
    """Every column of ``row`` but its notes."""
    return {
        field.attname: getattr(row, field.attname)
        for field in row._meta.concrete_fields
        if field.name not in ("notes", "note")
    }


def test_every_model_is_registered():
    for model in MODELS:
        assert model in admin.site._registry, model.__name__


def test_the_open_tables_keep_full_crud(superuser):
    request = request_by(superuser)
    for model in OPEN:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model.__name__
        assert model_admin.has_add_permission(request), model.__name__
        assert model_admin.has_change_permission(request), model.__name__
        assert model_admin.has_delete_permission(request), model.__name__


def test_what_was_charged_is_seen_but_never_added_nor_deleted(superuser):
    request = request_by(superuser)
    for model in CHARGED:
        model_admin = admin.site._registry[model]
        assert model_admin.has_view_permission(request), model.__name__
        assert not model_admin.has_add_permission(request), model.__name__
        assert not model_admin.has_delete_permission(request), model.__name__


def test_only_the_notes_of_a_sale_and_of_a_refund_are_editable(superuser):
    request = request_by(superuser)
    editable = {Sale: {"notes"}, Refund: {"note"}}
    for model in CHARGED:
        model_admin = admin.site._registry[model]
        columns = {field.name for field in model._meta.concrete_fields}
        readonly = set(model_admin.get_readonly_fields(request))
        assert columns - readonly == editable.get(model, set()), model.__name__
        assert model_admin.has_change_permission(request) is (model in editable), (
            model.__name__
        )


def test_ids_and_timestamps_are_read_only(superuser):
    request = request_by(superuser)
    for model in MODELS:
        readonly = set(admin.site._registry[model].get_readonly_fields(request))
        assert "id" in readonly, model.__name__
        for field in ("created_at", "updated_at"):
            if any(f.name == field for f in model._meta.get_fields()):
                assert field in readonly, (model.__name__, field)


def test_a_sale_shows_its_lines_and_payments_and_an_order_its_lines():
    assert admin.site._registry[Sale].inlines == [
        sale_admin.SaleLineInline,
        sale_admin.SalePaymentInline,
    ]
    assert admin.site._registry[Order].inlines == [sale_admin.OrderLineInline]
    assert admin.site._registry[Refund].inlines == [
        sale_admin.RefundPaymentInline,
        sale_admin.RefundLineInline,
    ]


def test_the_lines_and_payments_of_a_charge_or_a_refund_are_shown_read_only(superuser):
    request = request_by(superuser)
    for parent, inline_class in (
        (Sale, sale_admin.SaleLineInline),
        (Sale, sale_admin.SalePaymentInline),
        (Refund, sale_admin.RefundPaymentInline),
        (Refund, sale_admin.RefundLineInline),
    ):
        inline = inline_class(parent, admin.site)
        name = inline_class.__name__
        assert not inline.has_add_permission(request, None), name
        assert not inline.has_change_permission(request), name
        assert not inline.has_delete_permission(request), name
        assert set(inline.get_fields(request)) <= set(inline.get_readonly_fields(request)), name


def test_an_open_check_keeps_its_lines_editable(superuser):
    request = request_by(superuser)
    inline = sale_admin.OrderLineInline(Order, admin.site)
    assert inline.has_add_permission(request, None)
    assert inline.has_change_permission(request)
    assert inline.has_delete_permission(request)


def test_support_sees_the_service_and_the_voucher_of_a_line_and_repairs_them_on_an_open_check(
    superuser,
):
    request = request_by(superuser)
    voucher = {"service_id", "voucher_session_id", "voucher_grant_id", "voucher_name"}
    for model in (OrderLine, SaleLine):
        fields = set(admin.site._registry[model].get_fields(request))
        assert voucher <= fields, model.__name__
    order_line = admin.site._registry[OrderLine]
    assert {"voucher_remaining", "voucher_hold_until"} <= set(order_line.get_fields(request))
    assert not voucher & set(order_line.get_readonly_fields(request))
    assert voucher <= set(admin.site._registry[SaleLine].get_readonly_fields(request))


def test_deleting_the_day_counter_in_the_hub_admin_is_refused_and_the_next_charge_keeps_numbering(
    staff, product
):
    product()
    charge("admin-counter-0001")
    counter = SaleCounter.objects.get()
    answer = staff.post(url(counter, "delete"), {"post": "yes"}, **HOST)
    charge("admin-counter-0002")
    assert answer.status_code == 403
    assert list(Sale.objects.order_by("sequence").values_list("sequence", flat=True)) == [1, 2]
    assert SaleCounter.objects.get(pk=counter.pk).last == 2


@pytest.mark.parametrize("model", CHARGED, ids=lambda model: model.__name__)
def test_the_hub_admin_cannot_delete_what_was_charged(staff, charged, model):
    row = a_row(model)
    assert staff.get(url(row, "delete"), **HOST).status_code == 403
    assert staff.post(url(row, "delete"), {"post": "yes"}, **HOST).status_code == 403
    assert model.objects.filter(pk=row.pk).exists()


@pytest.mark.parametrize("model", CHARGED, ids=lambda model: model.__name__)
def test_the_hub_admin_offers_no_delete_selected_for_what_was_charged(staff, charged, model):
    row = a_row(model)
    page = staff.get(changelist(model), **HOST)
    assert page.status_code == 200
    assert b'value="delete_selected"' not in page.content
    staff.post(
        changelist(model),
        {"action": "delete_selected", "_selected_action": [str(row.pk)], "post": "yes"},
        **HOST,
    )
    assert model.objects.filter(pk=row.pk).exists()


@pytest.mark.parametrize("model", CHARGED, ids=lambda model: model.__name__)
def test_the_hub_admin_cannot_add_what_was_charged(staff, model):
    assert staff.get(f"{changelist(model)}add/", **HOST).status_code == 403


@pytest.mark.parametrize(
    ("model", "changes"),
    [
        (SaleLine, {"quantity": "5"}),
        (SalePayment, {"method_name": "Card"}),
        (SaleCounter, {"last": "0"}),
        (RefundPayment, {"amount": "1"}),
        (RefundLine, {"quantity": "2"}),
    ],
    ids=lambda value: value.__name__ if isinstance(value, type) else "",
)
def test_the_hub_admin_cannot_change_a_charged_line_payment_or_counter(
    staff, charged, model, changes
):
    row = a_row(model)
    before = fiscal(row)
    answer = save_change(staff, row, **changes)
    assert answer.status_code == 403
    assert fiscal(model.objects.get(pk=row.pk)) == before


@pytest.mark.parametrize(
    ("model", "note", "tampering"),
    [
        (
            Sale,
            "notes",
            {
                "number": "20200101-0999",
                "business_day": "2020-01-01",
                "total": "1",
                "status": "voided",
                "invoice_status": "issued",
                "customer_name": "Someone else",
                "lines-0-DELETE": "on",
                "payments-0-reference": "edited",
            },
        ),
        (
            Refund,
            "note",
            {
                "total": "1",
                "reason": "something else",
                "invoice_status": "issued",
                "lines-0-DELETE": "on",
                "payments-0-amount": "1",
            },
        ),
    ],
    ids=["Sale", "Refund"],
)
def test_the_hub_admin_changes_the_notes_of_a_charge_and_nothing_fiscal(
    staff, charged, model, note, tampering
):
    row = a_row(model)
    lines = [fiscal(line) for line in row.lines.all()]
    payments = [fiscal(payment) for payment in row.payments.all()]
    before = fiscal(row)
    answer = save_change(staff, row, **{note: "Called the customer"}, **tampering)
    assert answer.status_code == 302
    after = model.objects.get(pk=row.pk)
    assert getattr(after, note) == "Called the customer"
    assert fiscal(after) == before
    assert [fiscal(line) for line in after.lines.all()] == lines
    assert [fiscal(payment) for payment in after.payments.all()] == payments
