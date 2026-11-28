"""Models of the sale app.

- ``Order`` is the open check (mutable): its ``OrderLine`` rows freeze the price, the unit and the tax
  category when the line is added; ``version`` goes up with every change, so a charge can tell that the
  check moved under it. An order ends ``completed`` (charged to the last line) or ``voided``.
- ``Sale`` is the fiscal record a charge creates (immutable but for its void and its refunds): number of
  the business day, amounts, document type, customer; ``SaleLine`` keeps the fiscal copy of each line
  (category, rate, country, region and rule of tax) and ``SalePayment`` each tender.
- ``SaleCounter`` numbers the sales of a business day (``UPDATE … RETURNING``, never a sequence).
- ``Refund`` (with ``RefundPayment`` and ``RefundLine``) gives money back by tender, and the lines that
  return with it.
- ``PaymentMethod``, ``Settings`` (one row), ``Department`` and ``QuickNote`` are the till's catalogues.

Money is in whole cents and never negative; quantities are exact decimals with three places. Inventory
and Services are no requirement: a line keeps a copy of its product or its service, whose id is a plain
UUID, and a line paid with a voucher keeps the id of the Services session that pays it.

One module per responsibility, each imported here so that Django registers its models, in this order.
"""

from . import (
    fields as fields,
    payment_methods as payment_methods,
    settings as settings,
    departments as departments,
    orders as orders,
    sales as sales,
    payments as payments,
    numbering as numbering,
    refunds as refunds,
    voucher_sessions as voucher_sessions,
)
