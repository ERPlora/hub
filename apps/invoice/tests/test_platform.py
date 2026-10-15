"""ERPlora's own invoices as the SaaS posts them (``platform_payload()`` of saas-next/billing/services.py) → the
fields of an ``Invoice`` and its lines (``apps.invoice.platform``, pure: no database).

The qualification of each tax treatment is the old SaaS's (``fiscal/desglose.py``, ADR-0183), validated against the
AEAT: domestic S1 with its rate; OSS regime 17 and reverse charge, not subject by location (N2) with no rate nor
quota, the whole amount as its base; exempt E1. F1 with a recipient tax ID, a simplified F2 without one up to 400 €
(the old ``fiscal/invoice_type.py``), refused above.
"""

import copy
import datetime as dt
from decimal import Decimal

import pytest
from django.utils import translation

from apps.invoice import fiscal, platform

ISSUER = {
    "issuer_name": "ERPLORA CLOUD SL",
    "issuer_tax_id": "B27593136",
    "issuer_address": "Avda. de Lisboa, 17, 2º C, 28822 Coslada (Madrid)",
    "issuer_country": "ES",
}

#: A paid renewal of a Spanish business, as the SaaS's own test checks it (billing/tests/test_platform_invoices.py).
BODY = {
    "id": "019a0000-0000-7000-8000-000000000001",
    "kind": "invoice",
    "series": "ERP",
    "number": "ERP-2026-00123",
    "issued_on": "2026-10-15",
    "stripe_invoice_id": "in_1",
    "stripe_source_id": "",
    "rectification": None,
    "currency": "EUR",
    "language": "es",
    "net_cents": 2999,
    "tax_cents": 630,
    "total_cents": 3629,
    "tax_treatment": "domestic",
    "tax_country": "ES",
    "tax_rate": "21.00",
    "vat_included_reconciled": False,
    "vat_included_because_unverified": False,
    "business": {
        "id": "019a0000-0000-7000-8000-0000000000aa",
        "name": "Panadería López",
    },
    "recipient": {
        "name": "Panadería López SL",
        "tax_id": "B12345674",
        "tax_id_type": "",
        "tax_id_verified": False,
        "vat_consultation_number": "",
        "address": "Calle Mayor 1",
        "city": "Madrid",
        "postal_code": "28001",
        "country": "ES",
        "email": "ana@example.com",
    },
    "lines": [
        {
            "position": 1,
            "description": "Plan Starter (15 oct 2026 – 14 nov 2026)",
            "item_kind": "plan",
            "item_slug": "starter",
            "quantity": 1,
            "proration": False,
            "period_start": "2026-10-15",
            "period_end": "2026-11-14",
            "tax_category": "service.saas_subscription",
            "tax_treatment": "domestic",
            "tax_rate": "21.00",
            "net_cents": 2999,
            "tax_cents": 630,
            "total_cents": 3629,
        }
    ],
    "rectifies": None,
}


def body(**changes) -> dict:
    data = copy.deepcopy(BODY)
    data.update(changes)
    return data


def line(**changes) -> dict:
    data = copy.deepcopy(BODY["lines"][0])
    data.update(changes)
    return data


def fields(data: dict, **more) -> dict:
    return platform.to_invoice_fields(data, issuer=ISSUER, **more)


def test_the_number_is_the_saas_own_and_its_sequence_its_last_digits():
    got = fields(body())["invoice"]

    assert (got["series_code"], got["number"], got["sequence"], got["year"]) == (
        "ERP",
        "ERP-2026-00123",
        123,
        2026,
    )
    assert got["issue_date"] == got["operation_date"] == dt.date(2026, 10, 15)


def test_the_issuer_is_the_platform_hubs_and_the_recipient_the_payers_snapshot():
    got = fields(body())["invoice"]

    assert {key: got[key] for key in ISSUER} == ISSUER
    assert {
        key: got[key]
        for key in (
            "customer_name",
            "customer_tax_id",
            "customer_address",
            "customer_country",
            "customer_id_type",
        )
    } == {
        "customer_name": "Panadería López SL",
        "customer_tax_id": "B12345674",
        "customer_address": "Calle Mayor 1, 28001 Madrid",
        # A Spanish recipient keeps no country, as Invoicing's own documents (a NIF, not an IDOtro).
        "customer_country": "",
        "customer_id_type": "",
    }


def test_the_amounts_are_the_saas_cents_and_a_domestic_sale_is_subject_s1():
    got = fields(body())

    invoice = got["invoice"]
    assert (invoice["base_amount"], invoice["tax_amount"], invoice["total_amount"]) == (
        2999,
        630,
        3629,
    )
    assert invoice["currency"] == "EUR"
    assert invoice["tax_breakdown"] == [
        {
            "tax": "vat",
            "regime": "01",
            "qualification": "subject",
            "exempt_reason": "",
            "rate": "21.00",
            "surcharge_rate": "0.00",
            "base": 2999,
            "quota": 630,
            "surcharge_quota": 0,
        }
    ]
    assert (
        fiscal.audit(
            invoice["tax_breakdown"],
            got["tolerance"],
            base=invoice["base_amount"],
            tax=invoice["tax_amount"],
            invoice_type=invoice["invoice_type"],
        )
        is None
    )


def test_each_line_keeps_its_text_quantity_and_net_amount():
    [got] = fields(body())["lines"]

    assert got == {
        "description": "Plan Starter (15 oct 2026 – 14 nov 2026)",
        "quantity": Decimal(1),
        "unit_price": Decimal("2999.00"),
        "tax_rate": Decimal("21.00"),
        "tax_category_key": "service.saas_subscription",
        "base_amount": 2999,
        "tax_amount": 630,
        "total_amount": 3629,
    }


def test_the_operation_is_its_lines():
    second = line(
        position=2,
        description="Module Appointments",
        net_cents=1000,
        tax_cents=210,
        total_cents=1210,
    )
    data = body(lines=[line(), second], net_cents=3999, tax_cents=840, total_cents=4839)

    got = fields(data)["invoice"]

    assert (
        got["description"]
        == "Plan Starter (15 oct 2026 – 14 nov 2026), Module Appointments"
    )


def test_one_breakdown_entry_per_rate_with_the_lines_summed():
    lines = [
        line(position=1, net_cents=1000, tax_cents=210, total_cents=1210),
        line(position=2, net_cents=2000, tax_cents=420, total_cents=2420),
        line(
            position=3,
            tax_rate="10.00",
            net_cents=1000,
            tax_cents=100,
            total_cents=1100,
        ),
    ]
    data = body(lines=lines, net_cents=4000, tax_cents=730, total_cents=4730)

    breakdown = fields(data)["invoice"]["tax_breakdown"]

    assert [(item["rate"], item["base"], item["quota"]) for item in breakdown] == [
        ("21.00", 3000, 630),
        ("10.00", 1000, 100),
    ]


def test_a_proration_credit_line_carries_its_sign_in_the_quantity():
    credit = line(
        position=2,
        description="Unused time",
        proration=True,
        net_cents=-500,
        tax_cents=-105,
        total_cents=-605,
    )
    data = body(lines=[line(), credit], net_cents=2499, tax_cents=525, total_cents=3024)

    lines = fields(data)["lines"]

    assert (lines[1]["quantity"], lines[1]["unit_price"], lines[1]["base_amount"]) == (
        Decimal(-1),
        Decimal("500.00"),
        -500,
    )


@pytest.mark.parametrize(
    ("treatment", "regime", "qualification", "exempt_reason"),
    [
        ("reverse_charge", "01", "not_subject_location", ""),
        ("not_subject", "01", "not_subject_location", ""),
        ("oss", "17", "not_subject_location", ""),
        ("exempt", "01", "exempt", "E1"),
    ],
)
def test_without_spanish_vat_the_whole_amount_is_declared_without_rate_nor_quota(
    treatment, regime, qualification, exempt_reason
):
    # ADR-0183 (old SaaS, fiscal/desglose.py): N1/N2 and exempt carry neither TipoImpositivo nor CuotaRepercutida
    # (AEAT error 1237): an OSS sale declares the other state's VAT as part of the amount not subject here.
    taxed = treatment == "oss"
    data = body(
        tax_treatment=treatment,
        tax_country="DE" if taxed else "FR",
        tax_rate="19.00" if taxed else "0.00",
        net_cents=2999,
        tax_cents=570 if taxed else 0,
        total_cents=3569 if taxed else 2999,
        lines=[
            line(
                tax_treatment=treatment,
                tax_rate="19.00" if taxed else "0.00",
                tax_cents=570 if taxed else 0,
                total_cents=3569 if taxed else 2999,
            )
        ],
    )

    got = fields(data)
    invoice = got["invoice"]

    whole = 3569 if taxed else 2999
    assert invoice["tax_breakdown"] == [
        {
            "tax": "vat",
            "regime": regime,
            "qualification": qualification,
            "exempt_reason": exempt_reason,
            "rate": "0.00",
            "surcharge_rate": "0.00",
            "base": whole,
            "quota": 0,
            "surcharge_quota": 0,
        }
    ]
    assert (invoice["base_amount"], invoice["tax_amount"], invoice["total_amount"]) == (
        whole,
        0,
        whole,
    )
    [only] = got["lines"]
    assert (
        only["base_amount"],
        only["tax_amount"],
        only["total_amount"],
        only["tax_rate"],
    ) == (
        whole,
        0,
        whole,
        Decimal(0),
    )


def test_the_tax_notice_of_the_old_invoice_goes_in_its_notes_in_its_language():
    reverse = body(
        tax_treatment="reverse_charge",
        tax_country="FR",
        tax_rate="0.00",
        tax_cents=0,
        total_cents=2999,
        lines=[
            line(
                tax_treatment="reverse_charge",
                tax_rate="0.00",
                tax_cents=0,
                total_cents=2999,
            )
        ],
    )
    oss = body(
        tax_treatment="oss",
        tax_country="DE",
        tax_rate="19.00",
        tax_cents=570,
        total_cents=3569,
        language="en",
        lines=[
            line(tax_treatment="oss", tax_rate="19.00", tax_cents=570, total_cents=3569)
        ],
    )

    assert fields(reverse)["invoice"]["notes"] == (
        "Esta es una transacción B2B. El IVA es pagadero por el cliente bajo el mecanismo de inversión del sujeto "
        "pasivo."
    )
    assert fields(oss)["invoice"]["notes"] == "VAT 19.00% (DE)"
    assert fields(body())["invoice"]["notes"] == ""
    # The reader's language is left as it was.
    assert translation.get_language() == "en"


def test_a_foreign_recipient_keeps_its_country_and_a_uk_company_number_is_an_official_id():
    eu = body(
        recipient={
            **BODY["recipient"],
            "tax_id": "FR40303265045",
            "tax_id_type": "eu_vat",
            "country": "FR",
        }
    )
    uk = body(
        recipient={
            **BODY["recipient"],
            "tax_id": "12345678",
            "tax_id_type": "gb_business_id",
            "country": "GB",
        }
    )

    assert (
        fields(eu)["invoice"]["customer_country"],
        fields(eu)["invoice"]["customer_id_type"],
    ) == ("FR", "")
    assert (
        fields(uk)["invoice"]["customer_country"],
        fields(uk)["invoice"]["customer_id_type"],
    ) == ("GB", "04")


def test_with_a_recipient_tax_id_it_is_a_full_invoice_f1():
    assert fields(body())["invoice"]["invoice_type"] == "F1"


def test_without_a_tax_id_it_is_a_simplified_invoice_f2_up_to_400_euros():
    # The old fiscal/invoice_type.py (saas#1070): a subscription sold to someone without a tax ID is an F2.
    nobody = {**BODY["recipient"], "tax_id": ""}
    limit = line(net_cents=33058, tax_cents=6942, total_cents=40000)

    assert fields(body(recipient=nobody))["invoice"]["invoice_type"] == "F2"
    assert (
        fields(
            body(
                recipient=nobody,
                lines=[limit],
                net_cents=33058,
                tax_cents=6942,
                total_cents=40000,
            )
        )["invoice"]["invoice_type"]
        == "F2"
    )


def test_above_400_euros_without_a_tax_id_it_is_refused():
    nobody = {**BODY["recipient"], "tax_id": "  "}
    over = line(net_cents=34710, tax_cents=7289, total_cents=41999)

    with pytest.raises(platform.PlatformBodyRefused) as refused:
        fields(
            body(
                recipient=nobody,
                lines=[over],
                net_cents=34710,
                tax_cents=7289,
                total_cents=41999,
            )
        )

    assert refused.value.code == "invoice.platform_recipient_required"


def test_an_unknown_tax_treatment_is_refused_naming_it():
    data = body(tax_treatment="mystery", lines=[line(tax_treatment="mystery")])

    with pytest.raises(ValueError, match="mystery"):
        fields(data)


def test_a_line_without_its_own_treatment_takes_the_invoices():
    data = body(lines=[line(tax_treatment="")])

    assert fields(data)["invoice"]["tax_breakdown"][0]["qualification"] == "subject"


def test_a_number_without_a_sequence_is_refused():
    with pytest.raises(platform.PlatformBodyRefused) as refused:
        fields(body(number="ERP-2026-"))

    assert refused.value.code == "invoice.platform_number_invalid"


def test_lines_that_do_not_add_up_to_the_header_are_refused():
    with pytest.raises(platform.PlatformBodyRefused) as refused:
        fields(body(net_cents=3000, total_cents=3630))

    assert refused.value.code == "invoice.platform_totals_mismatch"


CREDIT_NOTE = {
    "id": "019a0000-0000-7000-8000-000000000002",
    "kind": "credit_note",
    "series": "ERPR",
    "number": "ERPR-2026-00007",
    "rectification": {"type": "R1", "reason": "Refund of the October renewal"},
    "net_cents": -2999,
    "tax_cents": -630,
    "total_cents": -3629,
    "lines": [line(net_cents=-2999, tax_cents=-630, total_cents=-3629)],
    "rectifies": {
        "id": BODY["id"],
        "number": "ERP-2026-00123",
        "issued_on": "2026-10-15",
    },
}


def test_a_credit_note_is_a_rectifying_invoice_by_differences_with_its_type_and_reason():
    got = fields(body(**CREDIT_NOTE), original_type="F1")["invoice"]

    assert (
        got["series_code"],
        got["sequence"],
        got["invoice_type"],
        got["rectification_kind"],
    ) == (
        "ERPR",
        7,
        "R1",
        "I",
    )
    assert got["description"] == "Refund of the October renewal"
    assert (got["base_amount"], got["tax_amount"], got["total_amount"]) == (
        -2999,
        -630,
        -3629,
    )


def test_a_credit_note_without_a_reason_names_its_lines():
    data = body(**{**CREDIT_NOTE, "rectification": {"type": "R4", "reason": ""}})

    got = fields(data, original_type="F1")["invoice"]

    assert (got["invoice_type"], got["description"]) == (
        "R4",
        "Plan Starter (15 oct 2026 – 14 nov 2026)",
    )


def test_a_credit_note_of_a_simplified_invoice_is_r5():
    # RD 1619/2012: the rectification of a simplified invoice is itself simplified (R5), whatever the SaaS chose.
    got = fields(body(**CREDIT_NOTE), original_type="F2")["invoice"]

    assert got["invoice_type"] == "R5"


def test_a_credit_note_needs_the_type_of_the_invoice_it_rectifies():
    with pytest.raises(platform.PlatformBodyRefused) as refused:
        fields(body(**CREDIT_NOTE))

    assert refused.value.code == "invoice.platform_original_unknown"
