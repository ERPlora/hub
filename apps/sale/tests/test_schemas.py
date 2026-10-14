"""The schemas of the sale app: what a request may say before any operation runs (the 422 by field)."""

from decimal import Decimal
from uuid import uuid7

import pytest
from pydantic import ValidationError

from apps.sale import schemas as s


def refused(schema, **data) -> set[str]:
    with pytest.raises(ValidationError) as error:
        schema.model_validate(data)
    return {
        ".".join(str(part) for part in item["loc"]) for item in error.value.errors()
    }


def test_every_input_field_is_described_for_the_assistant():
    for name in dir(s):
        schema = getattr(s, name)
        if (
            isinstance(schema, type)
            and issubclass(schema, s.Schema)
            and schema is not s.Schema
        ):
            for field_name, field in schema.model_fields.items():
                assert field.description, f"{name}.{field_name}"


def test_a_page_has_at_most_100_rows():
    assert refused(s.SaleListIn, limit=101) == {"limit"}
    assert refused(s.SaleListIn, limit=0) == {"limit"}
    assert s.SaleListIn().limit == 50


def test_a_quantity_is_positive_with_three_decimals_at_most():
    order = uuid7()
    assert s.OrderAddLineIn(order_id=order, product="COF").quantity == Decimal("1")
    assert s.OrderAddLineIn(
        order_id=order, product="COF", quantity="0.532"
    ).quantity == Decimal("0.532")
    assert refused(s.OrderAddLineIn, order_id=order, product="COF", quantity="0") == {
        "quantity"
    }
    assert refused(
        s.OrderAddLineIn, order_id=order, product="COF", quantity="0.0005"
    ) == {"quantity"}


def test_a_catalog_line_names_its_product_by_id_or_by_sku_or_name():
    order = uuid7()
    assert s.OrderAddLineIn(order_id=order, product_id=uuid7()).product is None
    assert s.OrderAddLineIn(order_id=order, product="Coffee").product == "Coffee"
    assert refused(s.OrderAddLineIn, order_id=order) == {""}


def test_an_open_price_line_needs_its_amount_and_a_department_or_a_tax_category():
    order = uuid7()
    line = s.OrderAddOpenLineIn(order_id=order, department="Fruit", unit_price=250)
    assert line.unit_price == 250 and line.quantity == Decimal("1")
    assert refused(s.OrderAddOpenLineIn, order_id=order, unit_price=250) == {""}
    assert refused(
        s.OrderAddOpenLineIn, order_id=order, department="Fruit", unit_price=-1
    ) == {"unit_price"}


def test_discounts_are_percentages_and_amounts_are_cents():
    order = uuid7()
    assert refused(s.OrderSetDiscountIn, order_id=order, discount_percent="100.5") == {
        "discount_percent"
    }
    assert refused(
        s.OrderSetDiscountIn, order_id=order, discount_percent="10", discount_amount=-1
    ) == {"discount_amount"}
    assert (
        s.OrderSetDiscountIn(order_id=order, discount_percent="12.5").discount_amount
        is None
    )


def test_a_charge_needs_its_attempt_key_and_something_to_charge():
    key = "pos-2026-abc"
    assert refused(s.CompleteIn, payments=[{"method": "cash"}]) >= {"idempotency_key"}
    assert refused(s.CompleteIn, idempotency_key="short", order_id=uuid7()) == {
        "idempotency_key"
    }
    assert refused(
        s.CompleteIn, idempotency_key="bad key with spaces", order_id=uuid7()
    ) == {"idempotency_key"}
    # An open check or loose lines, never both nor neither.
    assert refused(s.CompleteIn, idempotency_key=key) == {""}
    assert refused(
        s.CompleteIn, idempotency_key=key, order_id=uuid7(), lines=[{"product": "COF"}]
    ) == {""}
    sale = s.CompleteIn(idempotency_key=key, order_id=uuid7())
    assert sale.payments == [] and sale.document_type is None and sale.line_ids == []


def test_a_payment_names_its_method_and_never_a_negative_amount():
    assert refused(s.PaymentIn) == {""}
    assert refused(s.PaymentIn, method="cash", amount=0) == {"amount"}
    assert refused(s.PaymentIn, method="cash", tendered=-1) == {"tendered"}
    assert s.PaymentIn(method_id=uuid7(), amount=100).tendered is None


def test_the_customer_of_an_invoice_says_its_country_and_document_type():
    key = "pos-2026-abc"
    sale = s.CompleteIn(
        idempotency_key=key,
        order_id=uuid7(),
        customer_country="fr",
        customer_id_type="02",
    )
    assert sale.customer_country == "FR"
    assert refused(
        s.CompleteIn, idempotency_key=key, order_id=uuid7(), customer_country="FRA"
    ) == {"customer_country"}
    assert refused(
        s.CompleteIn, idempotency_key=key, order_id=uuid7(), customer_id_type="09"
    ) == {"customer_id_type"}


def test_a_void_and_a_refund_need_their_reason():
    assert refused(s.VoidIn, sale_id=uuid7(), reason="   ") == {"reason"}
    assert s.VoidIn(sale="20261014-0001", reason=" wrong ").reason == "wrong"
    refund = {
        "sale_id": uuid7(),
        "reason": "broken",
        "allocations": [{"payment_id": uuid7(), "amount": 100}],
    }
    assert s.RefundIn.model_validate(refund).lines == []
    assert refused(s.RefundIn, **(refund | {"reason": ""})) == {"reason"}
    assert refused(s.RefundIn, **(refund | {"allocations": []})) == {"allocations"}
    assert refused(
        s.RefundIn, **(refund | {"lines": [{"line_id": uuid7(), "quantity": "0"}]})
    ) == {"lines.0.quantity"}


def test_a_department_and_a_quick_note_have_their_lengths():
    assert refused(s.DepartmentIn, name="", tax_category_key="product.generic") == {
        "name"
    }
    assert refused(
        s.DepartmentIn, name="x" * 61, tax_category_key="product.generic"
    ) == {"name"}
    assert refused(s.QuickNoteIn, text="x" * 81) == {"text"}
    assert s.QuickNoteIn(text="  no salt  ").text == "no salt"


def test_settings_are_patched_field_by_field():
    patch = s.SettingsPatchIn(require_customer=True)
    assert patch.model_dump(exclude_unset=True) == {"require_customer": True}
    assert refused(s.SettingsPatchIn, max_discount_percent=101) == {
        "max_discount_percent"
    }
    assert refused(s.SettingsPatchIn, default_document_type="receipt") == {
        "default_document_type"
    }
    assert refused(s.SettingsPatchIn, unknown=True) == {"unknown"}


def test_a_new_payment_method_is_cash_unless_it_says_otherwise():
    assert s.PaymentMethodIn(name="Bizum").type == "cash"
    assert s.PaymentMethodIn(name="Bizum", type="other").type == "other"
    assert refused(s.PaymentMethodIn, name="Bizum", type="crypto") == {"type"}
