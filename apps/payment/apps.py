"""The payment app: the money that goes out of the business (to a supplier, a transfer, a refund that
is not a sale's), each payment with its reference of the day and its approval ladder, and the accounts
it is paid from (WORKBOOK.md). It is not the till's tenders: those are the sale app's."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class PaymentConfig(LiveAppConfig):
    name = "apps.payment"
    label = "payment"
    kind = "app"
    verbose_name = _("Payments")
    icon = "lucide:send"
    category = Category.SALES
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Outgoing payments to suppliers, with their reference and an approval step before they leave."
    )
    description = _(
        "Payments keeps the money that goes out of the business: what you pay a supplier, a transfer or "
        "a refund that is not a sale's. Each payment gets its own reference of the day and moves from "
        "draft to approved, sent and completed, or is cancelled with its reason, and keeps who recorded "
        "it, who approved it and when each step happened. You choose the account or the cash it is "
        "paid from. It moves no money and talks to no bank: you mark each step when it happened."
    )
    # In no template: the old catalogue retired it from the MVP; a business turns it on from the store.
    verticals = []
    # Nothing: the till's tenders are the sale app's and nothing here reads them (WORKBOOK «Decisión»).
    requires = []
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "payment.view_payment",
        "payment.add_payment",
        "payment.approve_payment",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). As in the old
    # module: the manager has all three; the employee only looks.
    role_permissions = {
        "hub_owner": ["payment.*"],
        "hub_admin": ["payment.*"],
        "hub_manager": ["payment.*"],
        "hub_employee": ["payment.view_payment"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only (UI-REQUESTS.md).
    navigation = [
        Nav("payments", _("Payments"), "lucide:send", "/payment/payments"),
        Nav("methods", _("Methods"), "ion:wallet-outline", "/payment/methods"),
    ]
