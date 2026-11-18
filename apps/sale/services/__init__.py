"""Write operations of the sale app: one operation = one transaction, with its events in the outbox.

Every write on an open check locks the check's row first (``select_for_update``) and raises its
``version``, so two devices are queued and a charge can tell the check moved under it. A charge locks
the check it charges, numbers the sale with its day's counter (``UPDATE … RETURNING``, in the same
transaction: a refusal never burns a number) and marks the lines it takes. A void and a refund lock the
sale's row: whichever comes first wins.

A line of a service may be paid with a customer's voucher (SALE-F27): the voucher's session is reserved,
released, delivered and given back by Services' own operations (``call_services``), inside the very
transaction of the write here, and the line keeps the session that pays it. Services is no requirement:
with it off, what needs it is refused (``sale.services_unavailable``) and taking a voucher or a line off
still works (the session comes back on its own at its deadline).
"""

from . import (
    charge_validation as charge_validation,
    checkout as checkout,
    discounts as discounts,
    documents as documents,
    line_vouchers as line_vouchers,
    order_actions as order_actions,
    order_lines as order_lines,
    orders as orders,
    printouts as printouts,
    reactions as reactions,
    refunds as refunds,
    sale_lines as sale_lines,
    settings as settings,
    voids as voids,
    vouchers as vouchers,
)
