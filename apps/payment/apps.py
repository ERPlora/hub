"""The payment app: the money that goes out of the business (to a supplier, a transfer, a refund that
is not a sale's), each payment with its reference of the day and its approval ladder, and the accounts
it is paid from (WORKBOOK.md). It is not the till's tenders: those are the sale app's."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav


class PaymentConfig(LiveAppConfig):
    name = "apps.payment"
    label = "payment"
    kind = "app"
    verbose_name = _("Payments")
    icon = "lucide:send"
    category = Category.SALES
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    # In no template: a business turns it on from the store.
    verticals = []
    # Nothing: the till's tenders are the sale app's and nothing here reads them (WORKBOOK «Decisión»).
    requires = []
    default_auto_field = "django.db.models.BigAutoField"
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). Where the business pays its suppliers from
    # is a payment method (payment.method), and so is its «cuenta bancaria» or «cuenta del banco», named by its phrases:
    # a «cuenta» alone is a table's check.
    assistant_synonyms = (
        (
            "method", "methods", "cuenta bancaria", "cuentas bancarias", "cuenta del banco", "cuentas del banco",
            "bank account", "bank accounts",
        ),
    )
    permissions = {
        "payment.view_payment": _("View payments and payment methods"),
        "payment.add_payment": _("Record payments, mark them sent or completed, and manage payment methods"),
        "payment.approve_payment": _("Approve and cancel payments"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The manager has
    # all three; the employee only looks.
    role_permissions = {
        "hub_owner": ["payment.*"],
        "hub_admin": ["payment.*"],
        "hub_manager": ["payment.*"],
        "hub_employee": ["payment.view_payment"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only (UI-REQUESTS.md).
    navigation = [
        Nav("payments", _("Payments"), "lucide:send", "/payment/payments", permission="payment.add_payment"),
        Nav("methods", _("Methods"), "ion:wallet-outline", "/payment/methods", permission="payment.add_payment"),
    ]
    help = Help(
        videos={"es": "GLFTc6kYTk8", "en": "ajeaqIejNK0"},
        flow_videos={
            "PAYMENT-F01": {"es": ["OK2ZK8gru1U"], "en": ["SfCZrov4jeA"]},
            "PAYMENT-F02": {"es": ["yorr2RF1IT0"], "en": ["hZyk-TWJJ9g"]},
            "PAYMENT-F03": {"es": ["yorr2RF1IT0"], "en": ["hZyk-TWJJ9g"]},
            "PAYMENT-F04": {"es": ["yorr2RF1IT0"], "en": ["hZyk-TWJJ9g"]},
            "PAYMENT-F05": {"es": ["zIv0o81BH58"], "en": ["MMZbN9sJ6Eo"]},
            "PAYMENT-F08": {"es": ["OK2ZK8gru1U"], "en": ["SfCZrov4jeA"]},
        },
    )

    fiscal_archive_models = ("PaymentMethod", "Payment")

    def fiscal_documents_kept(self) -> bool:
        """The platform asks (``base.tenancy.offboarding``) before it drops the database of a business that left: its
        outgoing payments are documents to keep, so the database stays; they go to the fiscal archive first
        (``fiscal_archive_models``)."""
        from apps.payment import queries  # the models are not loaded yet when this module is

        return queries.keeps_fiscal_documents()
