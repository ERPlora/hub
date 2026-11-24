"""Read operations of the sale app (``READ ONLY``) and the helpers the writes share with them.

The helpers that freeze a line (``freeze_product_line``, ``freeze_open_line``, ``freeze_service_line``)
read Inventory's product and units, and Services' service, through those apps' own operations, with
the caller's session: neither is a requirement of the sale app, so their tables are never
read here. ``call_app`` is the one door to an app sale does not require (Inventory's catalog, Services' catalog and
voucher sessions, Invoicing's documents, Cash register's drawer, Appointments' bookings), by the name of its operation:
the platform's ``base.operations.call``, with this app's own 409 when that app is not in the business. ``valuate`` is the one
valuation of a charge (``pricing.value`` over tax's closing), shared by the preview and the checkout.
"""

from . import (
    business as business,
    checkout as checkout,
    checkout_steps as checkout_steps,
    departments as departments,
    figures as figures,
    letterhead as letterhead,
    line_checks as line_checks,
    line_parts as line_parts,
    order_lines as order_lines,
    orders as orders,
    other_apps as other_apps,
    ownership as ownership,
    payment_methods as payment_methods,
    people as people,
    receipt_codes as receipt_codes,
    records as records,
    refunds as refunds,
    rows as rows,
    sales as sales,
    service_lines as service_lines,
    settings as settings,
)
