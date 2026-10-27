"""The invoice app: the numbered fiscal documents a sale leaves (ticket F2, invoice F1, the invoice that
substitutes a ticket F3 and the rectifying invoices R1–R5), their numbering series and the issuer copied
on each one (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep

from apps.invoice.events import ISSUER_UPDATED, SERIES_EVENTS


class InvoiceConfig(LiveAppConfig):
    name = "apps.invoice"
    label = "invoice"
    kind = "app"
    verbose_name = _("Invoicing")
    icon = "ion:receipt-outline"
    category = Category.SALES
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Every charged sale becomes a numbered ticket or invoice, corrected only by rectifying invoices."
    )
    description = _(
        "Invoicing turns every charged sale into its fiscal document: a simplified invoice for a ticket, "
        "a full invoice when the customer gives a tax ID, the full invoice that replaces a ticket the "
        "customer already took, and the rectifying invoice of every refund and void. Each document is "
        "numbered in its series and year with no gaps, carries the business as issuer, is never edited "
        "and is printed or saved as PDF. Invoices issued by hand, marked as paid and the numbering "
        "series are managed here too, ready for VeriFactu."
    )
    verticals = ["hair_salon", "restaurant"]
    # An invoice is born from a sale (its lines, amounts and frozen rules: a foreign key), its fiscal
    # keys are tax's rules, and its recipient is copied from a customer's card.
    requires = ["tax", "sale", "customer"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "invoice.view_invoice",
        "invoice.add_invoice",
        "invoice.rectify_invoice",
        "invoice.manage_series",
        "invoice.manage_issuer",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). Receiving the
    # issuer from the SaaS (``invoice.sync_issuer``) is declared by no role: only the system holds it.
    role_permissions = {
        "hub_owner": ["invoice.*"],
        "hub_admin": ["invoice.*"],
        "hub_manager": [
            "invoice.view_invoice",
            "invoice.add_invoice",
            "invoice.rectify_invoice",
            "invoice.manage_series",
        ],
        "hub_employee": ["invoice.view_invoice", "invoice.add_invoice"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only: the old `document-text-outline` and
    # `bookmark-outline` wait in UI-REQUESTS.md.
    navigation = [
        Nav("invoices", _("Invoices"), "ion:receipt-outline", "/invoice/invoices"),
        Nav("series", _("Series"), "ion:layers-outline", "/invoice/series"),
        Nav("issuer", _("Issuer"), "ion:storefront-outline", "/invoice/issuer"),
    ]
    # The Home's hooks (PLAN-HUB round 2026-10-21): the old hub's ⛔ «Your business details» (a core item there,
    # ``BLOCKING_KEYS``; here the issuer is Invoicing's, so its level is base's ``LEGAL_STEPS``) and the old module's
    # «Your invoice numbering» (it had no `widgets` nor `bell`), on the queries the Issuer and Series screens read.
    # The first is done with what issuing refuses to go without (``Issuer.configured``). The year's series are born
    # with the first document, so the second is recommended and only waits while the business has no series at all:
    # before its first document, the one moment to choose a prefix or continue another system's numbering; a new
    # year's series inherit the last one's (INVOICE-F14). Registered icons only: the old `business-outline` and
    # `bookmark-outline` wait in UI-REQUESTS.md.
    setup = [
        SetupStep(
            key="business_identity",
            operation="invoice.issuer.get",
            configured_when=[SetupCheck(field="configured", truthy=True)],
            title=_("Your business details"),
            description=_("Legal name, tax ID and address: without them you cannot issue an invoice."),
            icon="ion:storefront-outline",
            route="/invoice/issuer",
            permission="invoice.manage_issuer",
            order=40,
            required=True,
            refresh_on=[ISSUER_UPDATED],
        ),
        SetupStep(
            key="numbering",
            operation="invoice.numbering.status",
            configured_when=[SetupCheck(field="total_series", truthy=True)],
            title=_("Your invoice numbering"),
            description=_(
                "Before your first sale, check the prefix your invoice numbers will carry. If you are coming from "
                "another system, continue its numbering instead of starting again at 1."
            ),
            icon="ion:layers-outline",
            route="/invoice/series",
            permission="invoice.manage_series",
            order=50,
            required=False,
            refresh_on=SERIES_EVENTS,
        ),
    ]
