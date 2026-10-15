"""ERPlora's own invoices, as the SaaS posts them to its platform hub (PLAN-SAAS §4; ``platform_payload()`` of
saas-next/billing/services.py): the body → the fields of an ``Invoice`` and its lines. Pure: it reads and writes
nothing (``services.issue_platform`` writes, ``base.internal`` is the door).

- The number is the SaaS's own (``ERP-2026-00123``, ``ERPR-…`` for a credit note): its series, its year (of the issue
  date) and its sequence (the number's last digits). No series of the Hub is ever counted for it.
- The type: F1 with a recipient tax ID; without one, a simplified F2 up to 400 € (RD 1619/2012 art. 4), refused
  above (the old SaaS's ``fiscal/invoice_type.py``). A credit note is a rectifying invoice by differences with the
  SaaS's type (R1–R4), or R5 when it rectifies a simplified invoice.
- The breakdown: one entry per fiscal key, as the old SaaS declared it to the AEAT (``fiscal/desglose.py``,
  ADR-0183): a domestic sale is subject (S1) at its rate; OSS (regime 17), reverse charge and not subject are not
  subject by location (N2) and exempt is E1, all without rate nor quota, the whole amount of the line as its base
  (AEAT error 1237). The header is the sum of the breakdown, as every document of Invoicing.
- The notes: the tax notice the old invoice printed (reverse charge, OSS, not subject), in the document's language.
"""

import datetime as dt
import re
from collections import Counter
from decimal import Decimal

from django.utils import translation
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.invoice import fiscal

KINDS = ("invoice", "credit_note")
#: A rectifying invoice by differences (``Invoice.RectificationKind.DIFFERENCES``): the credit note's negative amounts.
DIFFERENCES = "I"
RECTIFYING_CHOICES = ("R1", "R2", "R3", "R4")
#: RD 1619/2012 art. 4: the general limit of a simplified invoice, in cents.
SIMPLIFIED_INVOICE_LIMIT = 40000
#: ``tax_treatment`` → (ClaveRegimen, qualification, exemption cause, with rate and quota); the old SaaS's table.
TREATMENTS = {
    "domestic": ("01", "subject", "", True),
    "oss": ("17", "not_subject_location", "", False),
    "reverse_charge": ("01", "not_subject_location", "", False),
    "not_subject": ("01", "not_subject_location", "", False),
    "exempt": ("01", "exempt", "E1", False),
}
#: A UK buyer named by its company number (the SaaS's ``gb_business_id``): an official ID of its country (L7 04).
UK_BUSINESS_ID_TYPE = "gb_business_id"
ID_IN_COUNTRY_OF_RESIDENCE = "04"
NAME_MAX_LENGTH = 120
TAX_ID_MAX_LENGTH = 20
DESCRIPTION_MAX_LENGTH = 500
_SEQUENCE = re.compile(r"(\d+)$")
_TWO_PLACES = Decimal("0.01")

REVERSE_CHARGE_NOTICE = _(
    "This is a B2B transaction. VAT is payable by the customer under the reverse charge mechanism."
)
OSS_NOTICE = _("VAT %(rate)s%% (%(country)s)")
NOT_SUBJECT_NOTICE = _("Not subject to VAT - %(country)s")


class PlatformBodyRefused(ValueError):
    """The body cannot be issued as it is; ``code`` says why (the SaaS keeps it with the invoice)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _treatment(name: str) -> tuple[str, str, str, bool]:
    try:
        return TREATMENTS[name]
    except KeyError:
        raise PlatformBodyRefused(
            "invoice.platform_tax_treatment_unknown",
            f"Unknown tax treatment {name!r}: expected one of {', '.join(TREATMENTS)}.",
        ) from None


def _sequence(number: str) -> int:
    found = _SEQUENCE.search(number or "")
    if found is None or int(found.group(1)) == 0:
        raise PlatformBodyRefused(
            "invoice.platform_number_invalid",
            f"The number {number!r} does not end in its sequence.",
        )
    return int(found.group(1))


def _recipient(recipient: dict) -> dict:
    tax_id = (recipient.get("tax_id") or "").strip()
    if len(tax_id) > TAX_ID_MAX_LENGTH:
        raise PlatformBodyRefused(
            "invoice.platform_tax_id_too_long",
            f"The recipient's tax ID has more than {TAX_ID_MAX_LENGTH} characters.",
        )
    country = (recipient.get("country") or "").strip().upper()
    town = " ".join(
        part
        for part in (
            (recipient.get("postal_code") or "").strip(),
            (recipient.get("city") or "").strip(),
        )
        if part
    )
    address = ", ".join(
        part for part in ((recipient.get("address") or "").strip(), town) if part
    )
    id_type = (
        ID_IN_COUNTRY_OF_RESIDENCE
        if tax_id and recipient.get("tax_id_type") == UK_BUSINESS_ID_TYPE
        else ""
    )
    return {
        "customer_name": (recipient.get("name") or "").strip()[:NAME_MAX_LENGTH],
        "customer_tax_id": tax_id,
        "customer_address": address[:400],
        # A Spanish recipient is named by its NIF and keeps no country, as Invoicing's own documents.
        "customer_country": "" if country == "ES" else country,
        "customer_id_type": id_type,
    }


def _invoice_type(body: dict, tax_id: str, original_type: str | None) -> str:
    if body["kind"] == "credit_note":
        if original_type is None:
            raise PlatformBodyRefused(
                "invoice.platform_original_unknown",
                "A credit note needs the invoice it rectifies.",
            )
        if original_type in ("F2", "R5"):
            return "R5"
        chosen = ((body.get("rectification") or {}).get("type") or "").strip()
        return chosen if chosen in RECTIFYING_CHOICES else "R1"
    if tax_id:
        return "F1"
    if int(body["total_cents"]) > SIMPLIFIED_INVOICE_LIMIT:
        raise PlatformBodyRefused(
            "invoice.platform_recipient_required",
            "Above 400 € a simplified invoice is not allowed: the recipient's tax ID is required.",
        )
    return "F2"


def _key(treatment: str, rate: Decimal) -> fiscal.FiscalKey:
    regime, qualification, exempt_reason, with_rate = _treatment(treatment)
    return fiscal.FiscalKey(
        tax="vat",
        regime=regime,
        cls=qualification,
        exempt_reason=exempt_reason,
        rate=rate if with_rate else Decimal(0),
    )


def _line(item: dict, treatment: str) -> tuple[fiscal.FiscalKey, dict]:
    rate = Decimal(str(item.get("tax_rate") or "0")).quantize(_TWO_PLACES)
    key = _key(treatment, rate)
    net, tax, total = (
        int(item["net_cents"]),
        int(item["tax_cents"]),
        int(item["total_cents"]),
    )
    if key.cls == fiscal.SUBJECT:
        base, quota = net, tax
    else:
        # No Spanish VAT is charged here: the whole amount of the line is its base, without quota.
        base, quota = total, 0
    quantity = Decimal(int(item.get("quantity") or 1))
    # Invoicing keeps the sign of a line in its quantity, never in its price.
    signed = -quantity if base < 0 else quantity
    unit_price = (Decimal(abs(base)) / quantity).quantize(_TWO_PLACES)
    return key, {
        "description": (item.get("description") or "").strip()[:255],
        "quantity": signed,
        "unit_price": unit_price,
        "tax_rate": key.rate,
        "tax_category_key": (item.get("tax_category") or "")[:80],
        "base_amount": base,
        "tax_amount": quota,
        "total_amount": base + quota,
    }


def _notes(body: dict) -> str:
    treatment = body["tax_treatment"]
    country = (body.get("tax_country") or "").strip().upper()
    with translation.override(body.get("language") or "es"):
        if treatment == "reverse_charge":
            return gettext(REVERSE_CHARGE_NOTICE)
        if treatment == "oss":
            return gettext(OSS_NOTICE) % {
                "rate": body.get("tax_rate"),
                "country": country,
            }
        if treatment == "not_subject":
            return gettext(NOT_SUBJECT_NOTICE) % {"country": country}
    return ""


def _check_totals(body: dict) -> None:
    lines = body.get("lines") or []
    if not lines:
        raise PlatformBodyRefused(
            "invoice.platform_no_lines", "The invoice has no lines."
        )
    for field in ("net_cents", "tax_cents", "total_cents"):
        if sum(int(item[field]) for item in lines) != int(body[field]):
            raise PlatformBodyRefused(
                "invoice.platform_totals_mismatch",
                f"The lines' {field} do not add up to the invoice's.",
            )
    if int(body["net_cents"]) + int(body["tax_cents"]) != int(body["total_cents"]):
        raise PlatformBodyRefused(
            "invoice.platform_totals_mismatch",
            "The net and the tax do not add up to the total.",
        )


def to_invoice_fields(
    body: dict, *, issuer: dict, original_type: str | None = None
) -> dict:
    """``{"invoice": …, "lines": […], "tolerance": {key: cents}}`` for ``body`` (the SaaS's ``platform_payload``,
    as JSON), issued by ``issuer`` (the ``issuer_*`` fields); ``original_type`` is the type of the invoice a credit
    note rectifies. ``PlatformBodyRefused`` (a ``ValueError`` with a ``code``) when it cannot be issued as it is."""
    if body.get("kind") not in KINDS:
        raise PlatformBodyRefused(
            "invoice.platform_kind_unknown", f"Unknown kind {body.get('kind')!r}."
        )
    _treatment(body["tax_treatment"])
    _check_totals(body)
    issued_on = dt.date.fromisoformat(str(body["issued_on"]))
    recipient = _recipient(body.get("recipient") or {})
    invoice_type = _invoice_type(body, recipient["customer_tax_id"], original_type)
    keyed = [
        _line(item, item.get("tax_treatment") or body["tax_treatment"])
        for item in sorted(
            body["lines"], key=lambda item: int(item.get("position") or 0)
        )
    ]
    groups: dict[fiscal.FiscalKey, list[int]] = {}
    for key, values in keyed:
        totals = groups.setdefault(key, [0, 0])
        totals[0] += values["base_amount"]
        totals[1] += values["tax_amount"]
    entries = [
        fiscal.entry(key, base=base, quota=quota)
        for key, (base, quota) in sorted(groups.items(), key=lambda pair: pair[0].order)
    ]
    lines = [values for _key, values in keyed]
    text = ", ".join(values["description"] for values in lines)
    reason = ((body.get("rectification") or {}).get("reason") or "").strip()
    is_credit_note = body["kind"] == "credit_note"
    invoice = {
        "invoice_type": invoice_type,
        "series_code": body["series"],
        "number": body["number"],
        "sequence": _sequence(body["number"]),
        "year": issued_on.year,
        "issue_date": issued_on,
        "operation_date": issued_on,
        **issuer,
        **recipient,
        "description": ((reason if is_credit_note and reason else text) or text)[
            :DESCRIPTION_MAX_LENGTH
        ],
        "notes": _notes(body),
        "base_amount": sum(item["base"] for item in entries),
        "tax_amount": sum(item["quota"] for item in entries),
        "total_amount": sum(item["base"] + item["quota"] for item in entries),
        "tax_breakdown": entries,
        "currency": body.get("currency") or "EUR",
        "rectification_kind": DIFFERENCES if is_credit_note else "",
    }
    # Each key's quota may stray by a cent per line from its base × rate (the SaaS rounds line by line).
    tolerance = dict(Counter(key for key, _values in keyed))
    return {"invoice": invoice, "lines": lines, "tolerance": tolerance}
