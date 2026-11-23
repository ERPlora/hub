"""The issuer of a document as it is read and printed (``tests/test_document_issuer.py``). Pure: it reads the copy an
invoice keeps and writes nothing.

``issuer_tax_id`` is the tax ID as kept, the one VeriFactu declares (``IDEmisorFactura``) and the QR carries: the AEAT
refuses it with a country prefix. ``issuer_vat_number`` is the one the paper prints: the issuer's EU VAT number
(``ESB27593136``) while it is registered for intra-EU operations (the ROI), on every invoice, domestic ones too; any
other issuer prints its tax ID as kept. A business says it is registered on its issuer (``intra_eu_operator``), and
each document keeps that mark with its copy of the issuer; ERPlora always is, known by the platform issuer's tax ID
(``PLATFORM_ISSUER_TAX_ID``).
"""

from django.conf import settings

from apps.customer.tax_ids import HOME_COUNTRY, vat_number


def issuer_vat_number(tax_id: str, country: str, *, intra_eu_operator: bool = False) -> str:
    """What a document prints as the tax ID of an issuer with ``tax_id`` in ``country`` (empty = Spain)."""
    if not intra_eu_operator and tax_id != settings.PLATFORM_ISSUER_TAX_ID:
        return tax_id
    return vat_number(tax_id, country or HOME_COUNTRY)


def document_issuer(invoice) -> dict:
    """The issuer fields of an ``InvoiceOut`` for ``invoice``, as it was when issued."""
    return {
        "issuer_name": invoice.issuer_name,
        "issuer_tax_id": invoice.issuer_tax_id,
        "issuer_vat_number": issuer_vat_number(
            invoice.issuer_tax_id, invoice.issuer_country, intra_eu_operator=invoice.issuer_intra_eu_operator
        ),
        "issuer_address": invoice.issuer_address,
        "issuer_country": invoice.issuer_country,
    }


def printed_issuer(issuer) -> dict:
    """What an ``IssuerOut`` says of the ROI for ``issuer``: the mark and the tax ID its documents print."""
    return {
        "intra_eu_operator": issuer.intra_eu_operator,
        "vat_number": issuer_vat_number(issuer.tax_id, issuer.country, intra_eu_operator=issuer.intra_eu_operator),
    }
