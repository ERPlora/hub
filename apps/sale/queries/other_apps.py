"""The one door to an app Sales does not require, by the name of its operation."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, PermissionDenied
from live.operations import UnknownOperation

from base.operations import call

CATALOG_UNAVAILABLE = _(
    "Inventory's catalog cannot be read right now, so no product can be sold. Try again in a moment."
)


SERVICES_UNAVAILABLE = _(
    "Services is not active in this business: its services cannot be sold nor its vouchers used. Take the "
    "voucher off the line to charge it."
)
INVOICE_UNAVAILABLE = _(
    "Invoicing is not active in this business: the sale is a ticket without a fiscal document."
)
CASH_REGISTER_UNAVAILABLE = _("Cash register is not active in this business.")
MODIFIER_UNAVAILABLE = _(
    "Modifiers is not active in this business: this product cannot take options. Add it without them."
)
MENUS_UNAVAILABLE = _(
    "Menus and combos is not active in this business: menus cannot be sold. Sell their dishes on their own."
)
APPOINTMENT_UNAVAILABLE = _("Appointments is not active in this business.")
STAFF_UNAVAILABLE = _("Staff is not active in this business.")


#: What a 409 of an app sale does not require says when that app is not in this business.
UNAVAILABLE = {
    "sale.catalog_unavailable": CATALOG_UNAVAILABLE,
    "sale.services_unavailable": SERVICES_UNAVAILABLE,
    "sale.invoice_unavailable": INVOICE_UNAVAILABLE,
    "sale.cash_register_unavailable": CASH_REGISTER_UNAVAILABLE,
    "sale.appointment_unavailable": APPOINTMENT_UNAVAILABLE,
    "sale.modifier_unavailable": MODIFIER_UNAVAILABLE,
    "sale.combo_unavailable": MENUS_UNAVAILABLE,
    "sale.staff_unavailable": STAFF_UNAVAILABLE,
}


def call_app(ctx: OperationContext, name: str, data: dict, unavailable_code: str):
    """Runs the operation ``name`` of an app sale does not require, for the caller, through the platform's one door
    (``base.operations.call``, BASE-F84): its permission and its active-app check apply, its refusals reach the caller
    as they are, an input it does not take is the caller's 422, and nested in a write it runs in a savepoint. Inside a
    command a manager approved, a command of another app goes with it, by the platform's rule. The app off or absent →
    409 ``unavailable_code``, said as this app says it."""
    return call(ctx, name, data, unavailable=Conflict(str(UNAVAILABLE[unavailable_code]), code=unavailable_code))


def answer_if_on(ctx: OperationContext, name: str, data: dict):
    """The answer of the read ``name`` of an app Sales does not require, for the caller (``call_app``), or ``None`` when
    that app is absent, off or not theirs to read: for what only adds to what Sales says on its own."""
    try:
        return call(ctx, name, data)
    except (UnknownOperation, AppInactive, PermissionDenied):
        return None


def call_services(ctx: OperationContext, name: str, data: dict):
    """Services' operation ``name`` (``call_app``); off or absent → ``sale.services_unavailable``.

    Its refusals (a voucher spent, a session no longer held…) reach the caller as they are."""
    return call_app(ctx, name, data, "sale.services_unavailable")
