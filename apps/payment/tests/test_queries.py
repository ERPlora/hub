"""Read operations of the payment app: the payments (search, filters, order, pages), one payment, and
the methods.

The filter cases come from the old module's tests: typing a piece of the reference (its last digits,
its date) finds the payment (payments#21, `text_filters_narrow_by_fragment`), the beneficiary narrows
by fragment too, and every filter box the screen paints has its filter in the query's input
(`filter_boxes_match_the_manifest`).
"""

import datetime as dt
import re
from pathlib import Path

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.payment.schemas import (
    MethodListIn,
    MethodOut,
    MethodRefIn,
    MethodPage,
    PaymentListIn,
    PaymentOut,
    PaymentPage,
    PaymentRefIn,
)

from .conftest import ctx_for, make_method, make_payment

pytestmark = pytest.mark.django_db

OPERATIONS_TS = Path(__file__).resolve().parents[1] / "frontend" / "operations.d.ts"


def run(name, data=None, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), data if data is not None else op.input())


def refs(page) -> list[str]:
    return [row.reference for row in page.rows]


@pytest.mark.parametrize(
    ("name", "input", "output"),
    [
        ("payment.payment.list", PaymentListIn, PaymentPage),
        ("payment.payment.get", PaymentRefIn, PaymentOut),
        ("payment.method.list", MethodListIn, MethodPage),
        ("payment.method.get", MethodRefIn, MethodOut),
    ],
)
def test_declarations(name, input, output):
    op = get(name)
    assert (op.kind, op.input, op.output, op.permission, op.expose_api) == (
        "query",
        input,
        output,
        "payment.view_payment",
        True,
    )


@pytest.fixture
def ledger():
    """Four payments of two methods, on three days."""
    bank = make_method("BBVA account")
    cash = make_method("Cash drawer", method_type="cash")
    make_payment(
        bank,
        reference="PAY-20260821-0003",
        beneficiary_name="Proveedor Norte SL",
        payment_date=dt.date(2026, 8, 21),
        amount=125_50,
        supplier_invoice_ref="F-2026-118",
        beneficiary_iban="ES9121000418450200051332",
        concept="Tintes de agosto",
    )
    make_payment(
        bank,
        reference="PAY-20260821-0004",
        beneficiary_name="Suministros Ana",
        payment_date=dt.date(2026, 8, 21),
        amount=40_00,
        status="approved",
    )
    make_payment(
        cash,
        reference="PAY-20250114-0999",
        beneficiary_name="Proveedor Sur SA",
        payment_date=dt.date(2025, 1, 14),
        amount=9_99,
        status="completed",
    )
    make_payment(
        cash,
        reference="PAY-20261001-0001",
        beneficiary_name="Lavandería López",
        payment_date=dt.date(2026, 10, 1),
        amount=60_00,
        currency="USD",
        status="cancelled",
        cancel_reason="Duplicated",
    )
    return bank, cash


def listed(**params) -> list[str]:
    return refs(run("payment.payment.list", PaymentListIn(**params)))


# The list


def test_the_list_is_newest_payment_date_first(ledger):
    page = run("payment.payment.list")
    assert refs(page) == [
        "PAY-20261001-0001",
        "PAY-20260821-0004",
        "PAY-20260821-0003",
        "PAY-20250114-0999",
    ]
    assert (page.total, page.limit, page.offset) == (4, 50, 0)


def test_a_row_carries_everything_a_payment_says(ledger):
    bank, _ = ledger
    row = next(
        r
        for r in run("payment.payment.list").rows
        if r.reference == "PAY-20260821-0003"
    )
    assert row.method_id == bank.id
    assert row.method_name == "BBVA account"
    assert (row.amount, row.currency, row.status) == (125_50, "EUR", "draft")
    # The list (and its live stream) never carries a whole IBAN: only its country and last four.
    assert (row.beneficiary_iban, row.supplier_invoice_ref, row.concept) == (
        "ES** **** **** **** **** 1332",
        "F-2026-118",
        "Tintes de agosto",
    )
    cancelled = next(
        r for r in run("payment.payment.list").rows if r.status == "cancelled"
    )
    assert cancelled.cancel_reason == "Duplicated"


def test_pages_never_overlap(ledger):
    first = listed(limit=2)
    second = listed(limit=2, offset=2)
    assert len(first) == len(second) == 2
    assert not set(first) & set(second)


@pytest.mark.parametrize(
    ("typed", "found"),
    [
        # What a person remembers is the last digits or the date, never the whole reference.
        ("0003", ["PAY-20260821-0003"]),
        ("20260821", ["PAY-20260821-0004", "PAY-20260821-0003"]),
        ("PAY-20260821-0003", ["PAY-20260821-0003"]),
        ("pay-20250114", ["PAY-20250114-0999"]),
    ],
)
def test_a_piece_of_the_reference_finds_the_payment(ledger, typed, found):
    assert listed(reference=typed) == found
    assert listed(search=typed) == found


def test_the_beneficiary_narrows_by_fragment_whatever_the_case(ledger):
    assert listed(beneficiary_name="proveedor") == [
        "PAY-20260821-0003",
        "PAY-20250114-0999",
    ]
    assert listed(search="suministros") == ["PAY-20260821-0004"]


def test_the_search_reads_the_supplier_invoice_too(ledger):
    assert listed(search="f-2026") == ["PAY-20260821-0003"]


def test_the_concept_narrows_by_fragment(ledger):
    assert listed(concept="tintes") == ["PAY-20260821-0003"]


def test_exact_filters(ledger):
    bank, cash = ledger
    assert listed(status="approved") == ["PAY-20260821-0004"]
    assert listed(method_id=cash.id) == ["PAY-20261001-0001", "PAY-20250114-0999"]
    assert listed(method="bbva ACCOUNT") == ["PAY-20260821-0004", "PAY-20260821-0003"]
    assert listed(currency="usd") == ["PAY-20261001-0001"]
    assert listed(beneficiary_iban="es91 2100 0418 4502 0005 1332") == [
        "PAY-20260821-0003"
    ]
    assert listed(supplier_invoice_ref="f-2026-118") == ["PAY-20260821-0003"]
    # A piece of the invoice number is not the invoice: an exact filter stays exact.
    assert listed(supplier_invoice_ref="F-2026") == []


def test_ranges_include_both_ends(ledger):
    assert listed(
        payment_date_from=dt.date(2026, 8, 21), payment_date_to=dt.date(2026, 8, 21)
    ) == [
        "PAY-20260821-0004",
        "PAY-20260821-0003",
    ]
    assert listed(payment_date_to=dt.date(2025, 12, 31)) == ["PAY-20250114-0999"]
    assert listed(amount_min=40_00, amount_max=60_00) == [
        "PAY-20261001-0001",
        "PAY-20260821-0004",
    ]
    assert listed(amount_min=100_00) == ["PAY-20260821-0003"]


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        (
            "amount",
            [
                "PAY-20250114-0999",
                "PAY-20260821-0004",
                "PAY-20261001-0001",
                "PAY-20260821-0003",
            ],
        ),
        (
            "-amount",
            [
                "PAY-20260821-0003",
                "PAY-20261001-0001",
                "PAY-20260821-0004",
                "PAY-20250114-0999",
            ],
        ),
        (
            "beneficiary_name",
            [
                "PAY-20261001-0001",
                "PAY-20260821-0003",
                "PAY-20250114-0999",
                "PAY-20260821-0004",
            ],
        ),
        (
            "reference",
            [
                "PAY-20250114-0999",
                "PAY-20260821-0003",
                "PAY-20260821-0004",
                "PAY-20261001-0001",
            ],
        ),
        (
            "payment_date",
            [
                "PAY-20250114-0999",
                "PAY-20260821-0003",
                "PAY-20260821-0004",
                "PAY-20261001-0001",
            ],
        ),
    ],
)
def test_the_order_of_every_column(ledger, sort, expected):
    assert listed(sort=sort) == expected


def test_the_method_name_sorts_too(ledger):
    assert listed(sort="method_name")[:2] == ["PAY-20260821-0003", "PAY-20260821-0004"]


def test_an_employee_may_look():
    assert run("payment.payment.list", role="hub_employee").total == 0


def test_nobody_without_the_view_permission(ledger):
    with pytest.raises(PermissionDenied):
        run("payment.payment.list", role="hub_employee", permissions=set())


def ts_fields(interface: str) -> set[str]:
    """The fields of ``interface`` in the pages' typed operations (``frontend/operations.d.ts``)."""
    source = OPERATIONS_TS.read_text()
    found = re.search(
        rf"export interface {interface}(?: extends (\w+))? \{{(.*?)\n\}}", source, re.S
    )
    assert found, f"{interface} is not in operations.d.ts"
    fields = set(re.findall(r"^\s+(\w+)\??:", found.group(2), re.M))
    return fields | (ts_fields(found.group(1)) if found.group(1) else set())


@pytest.mark.parametrize(
    ("interface", "schema"),
    [("PaymentListIn", PaymentListIn), ("MethodListIn", MethodListIn)],
)
def test_the_pages_filter_with_the_declared_filters_only(interface, schema):
    # The old `filter_boxes_match_the_manifest`: a box the query does not declare does nothing. The
    # pages build their query as these TypeScript types (vue-tsc checks it); the types are the schema.
    assert ts_fields(interface) == set(schema.model_fields)


# One payment


def test_a_payment_by_its_id_or_its_reference(ledger):
    payment = run("payment.payment.get", PaymentRefIn(reference="pay-20260821-0003"))
    assert payment.beneficiary_name == "Proveedor Norte SL"
    # One payment, asked for: its whole IBAN.
    assert payment.beneficiary_iban == "ES9121000418450200051332"
    assert (
        run("payment.payment.get", PaymentRefIn(id=payment.id)).reference
        == "PAY-20260821-0003"
    )


def test_an_unknown_payment_is_not_found(ledger):
    with pytest.raises(NotFound) as caught:
        run("payment.payment.get", PaymentRefIn(reference="PAY-19990101-0001"))
    assert caught.value.code == "payment.payment_not_found"


# The methods


def test_the_methods_by_name_with_their_state():
    make_method("Zeta card", method_type="card", bank_account_ref="*1234")
    make_method("Cash drawer", method_type="cash", is_active=False)
    page = run("payment.method.list", MethodListIn())
    assert [
        (m.name, m.method_type, m.bank_account_ref, m.is_active) for m in page.rows
    ] == [
        ("Cash drawer", "cash", "", False),
        ("Zeta card", "card", "*1234", True),
    ]
    assert page.total == 2


def test_the_method_list_masks_the_account_and_the_method_gives_it_whole():
    bank = make_method("BBVA account", bank_account_ref="ES91 2100 0418 4502 0005 1332")
    make_method("Card", method_type="card", bank_account_ref="*1234")
    rows = {m.name: m.bank_account_ref for m in run("payment.method.list", MethodListIn()).rows}
    assert rows == {"BBVA account": "ES** **** **** **** **** 1332", "Card": "*1234"}
    whole = run("payment.method.get", MethodRefIn(id=bank.id))
    assert whole.bank_account_ref == "ES91 2100 0418 4502 0005 1332"
    assert run("payment.method.get", MethodRefIn(method="bbva")).id == bank.id


@pytest.mark.parametrize(
    ("value", "masked"),
    [
        ("ES9121000418450200051332", "ES** **** **** **** **** 1332"),
        ("es91 2100 0418 4502 0005 1332", "ES** **** **** **** **** 1332"),
        ("DE89370400440532013000", "DE** **** **** **** **30 00"),
        ("BBVA cuenta 1332", "************1332"),
        ("*1234", "*1234"),
        ("1234", "1234"),
        ("", ""),
    ],
)
def test_mask_account(value, masked):
    from apps.payment.queries import mask_account

    assert mask_account(value) == masked


def test_the_methods_filter_by_type_state_and_search():
    make_method("BBVA account", bank_account_ref="ES91…1332")
    make_method("Cash drawer", method_type="cash", is_active=False)
    names = lambda **p: [
        m.name for m in run("payment.method.list", MethodListIn(**p)).rows
    ]  # noqa: E731
    assert names(is_active=True) == ["BBVA account"]
    assert names(is_active=False) == ["Cash drawer"]
    assert names(method_type="cash") == ["Cash drawer"]
    assert names(search="1332") == ["BBVA account"]
    assert names(search="drawer") == ["Cash drawer"]
    assert names(sort="-name") == ["Cash drawer", "BBVA account"]


def test_find_method_by_name_exact_else_the_only_one_containing_it():
    from apps.payment.queries import find_method

    bank = make_method("BBVA account")
    make_method("Cash drawer", method_type="cash")
    make_method("Cash box", method_type="cash")
    assert find_method(None, "bbva").pk == bank.pk
    assert find_method(None, "BBVA ACCOUNT").pk == bank.pk
    with pytest.raises(Conflict) as caught:
        find_method(None, "cash")
    assert caught.value.code == "payment.method_ambiguous"
    assert "Cash box" in caught.value.message and "Cash drawer" in caught.value.message
    with pytest.raises(NotFound) as missing:
        find_method(None, "Santander")
    assert missing.value.code == "payment.method_not_found"
