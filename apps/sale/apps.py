"""The sale app: the till (open checks and their lines), the immutable sales it charges, their voids and
refunds, the payment methods, the departments of the open price, the quick notes and the till settings
(WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav, Widget

from apps.sale.events import FIGURE_EVENTS, SALE_EVENTS
from base.allergens import ALLERGENS


class SaleConfig(LiveAppConfig):
    name = "apps.sale"
    label = "sale"
    kind = "app"
    verbose_name = _("Sales & POS")
    icon = "ion:cart-outline"
    category = Category.SALES
    premium = False
    # The app store's texts, which register_apps writes to shared.app.
    summary = _(
        "The till: build the check, charge it in cash, by card or split, and void or refund a sale."
    )
    description = _(
        "Sales & POS is the business's cash register. Build the check by tapping articles or typing an "
        "open price by section, add notes, discounts and comps, park it and pick it up again, charge "
        "it whole or in parts, in cash with change, by card or split between several methods, as a "
        "ticket or a full invoice. Every sale gets its number of the day and its VAT line by line, is "
        "never edited, and is corrected by voiding it or refunding it, whole or in part. Inventory "
        "lowers the stock and Customers adds the purchase on their own."
    )
    verticals = ["hair_salon", "restaurant"]
    # Every line is priced with tax's rules and a sale keeps its customer's card (foreign keys).
    # Inventory is optional: its products are read through its own operations.
    requires = ["tax", "customer"]
    default_auto_field = "django.db.models.BigAutoField"
    # The customer's allergy by the allergens' names: no field of the models labels them, so the card would say codes.
    choices = {"allergy": ALLERGENS}
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). A «cuenta», a check or a tab is a table's
    # open check (sale.order), never the person's account (what it is in erplora.com's panel); a ticket or a receipt is
    # a sale's, as the till's screens say («Tiques hoy», «Tique medio», the «Tique» it prints), never the kitchen's,
    # which is its «comanda». A text set up «para marcarlo rápido» is a quick note (sale.quick_note), only after «para»:
    # «quiero marcarla rápido como pagada» marks an invoice, and «un aviso rápido» is also a message to a customer.
    assistant_synonyms = (
        ("cuenta", "check", "tab", "order"),
        ("ticket", "tique", "recibo", "receipt", "sale"),
        ("quick", "para marcarlo rápido", "para marcarla rápido"),
    )
    permissions = [
        "sale.view_sale",
        "sale.add_sale",
        "sale.take_payment",
        "sale.sell_open_price",
        "sale.discount_over_limit",
        "sale.void_sale",
        "sale.refund_sale",
        "sale.view_paymentmethod",
        "sale.add_paymentmethod",
        "sale.view_all_sales",
        "sale.view_reports",
        "sale.manage_settings",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old cashier
    # (an employee who also charges) is the employee now.
    role_permissions = {
        "hub_owner": ["sale.*"],
        "hub_admin": ["sale.*"],
        "hub_manager": ["sale.*"],
        "hub_employee": [
            "sale.view_sale",
            "sale.add_sale",
            "sale.take_payment",
            "sale.view_paymentmethod",
        ],
    }
    # What a manager approves on the spot with their PIN on the cashier's own device (BASE-F84;
    # Square, Toast, Lightspeed and Shopify's manager override), in the words the dialog «An approval
    # is needed» says: every command of the till whose permission the employee lacks. Who holds it is never asked.
    approvals = {
        "sale.sale.void": _("Void a sale"),
        "sale.sale.refund": _("Refund a sale"),
        "sale.order.void_line": _("Void an item already sent to the kitchen"),
        "sale.order.set_line_discount_over_limit": _("Discount a line above the maximum"),
        "sale.order.set_discount_over_limit": _("Discount the check above the maximum"),
        "sale.sale.complete_over_limit": _("Charge with a discount above the maximum"),
        "sale.order.add_open_line": _("Sell at an open price"),
        "sale.order.void_ordered": _("Delete an open check with something on it"),
    }
    # The same, with how much is approved, from the figures of that very request (BASE-F84), so the manager never
    # approves blind on «above the maximum»: the first sentence whose every hole fills, an amount in the business's
    # currency; none fills (a zero, an empty figure, a check's own discount at its charge), the words above. Void,
    # refund, void an item and delete a check have no figure on the first level of their input.
    approval_figures = {
        "sale.order.set_line_discount_over_limit": [_("Discount a line by {discount_percent, percent}")],
        "sale.order.set_discount_over_limit": [
            _("Discount the check by {discount_percent, percent} and {discount_amount, money}"),
            _("Discount the check by {discount_percent, percent}"),
            _("Discount the check by {discount_amount, money}"),
        ],
        "sale.sale.complete_over_limit": [
            _("Charge with a discount of {discount_percent, percent} and {discount_amount, money}"),
            _("Charge with a discount of {discount_percent, percent}"),
            _("Charge with a discount of {discount_amount, money}"),
        ],
        "sale.order.add_open_line": [_("Sell at an open price of {unit_price, money}")],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. Registered icons only: the old `storefront` (filled) and
    # `chatbubble-ellipses-outline` wait in UI-REQUESTS.md. The departments of the open price read
    # «Sections»: the old «Departments» was one word wider than a fifth of a phone's tabbar.
    navigation = [
        Nav("pos", _("Sell"), "ion:storefront-outline", "/sale/pos", permission="sale.add_sale"),
        Nav("sales", _("Sales"), "ion:cart-outline", "/sale/sales", permission="sale.view_sale"),
        Nav(
            "quick_notes",
            _("Quick notes"),
            "ion:chatbubbles-outline",
            "/sale/quick-notes",
            permission="sale.manage_settings",
        ),
        Nav("departments", _("Sections"), "ion:grid-outline", "/sale/departments", permission="sale.manage_settings"),
        Nav("settings", _("Settings"), "ion:settings-outline", "/sale/settings", permission="sale.manage_settings"),
    ]
    help = Help(
        videos={"es": "DOqTuM2fCJE", "en": "uFhhYJm3Mr8"},
        flow_videos={
            "SALE-F01": {"es": ["0j9NMnpgXWM"], "en": ["TALKAH4xCLM"]},
            "SALE-F02": {"es": ["6IaIDRuKHzk"], "en": ["glc7T7Xpyw0"]},
            "SALE-F03": {"es": ["4iMjcVUNlGQ"], "en": ["FjqB1ra8qPQ"]},
            "SALE-F04": {"es": ["QZIskHcvbx4"], "en": ["WBdK2Z-XHOQ"]},
            "SALE-F05": {"es": ["QZIskHcvbx4"], "en": ["WBdK2Z-XHOQ"]},
            "SALE-F11": {"es": ["gtsNNFvYHIw"], "en": ["yViCguWhBP8"]},
            "SALE-F13": {"es": ["VkHmRSouS8U"], "en": ["yQGyb_bvMi8"]},
            "SALE-F14": {"es": ["kG1MT9VEMjo"], "en": ["B_-hW7QysXU"]},
            "SALE-F15": {"es": ["ADneSwlsnlg"], "en": ["8vLwV_6ILUQ"]},
        },
    )
    # The Home's panels, on the queries Sales' own screen reads, each refreshed by the events live.py re-runs its query
    # on; each figure in the colour of data of its measure, the same on every screen (sales 1, tickets 2). Registered
    # icons only: the old `trending-up-outline` and `bar-chart-outline` wait in UI-REQUESTS.md. No steps of «Finish
    # setting up your business» nor counters of the bell: the old module had none.
    widgets = [
        Widget(
            key="today",
            title=_("Today's sales"),
            icon="ion:cash-outline",
            size="sm",
            permission="sale.view_reports",
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="kpi",
            operation="sale.sale.today",
            map={"value": "total"},
            options={"format": "currency", "tone": 1},
        ),
        Widget(
            key="tickets_today",
            title=_("Today's tickets"),
            icon="ion:receipt-outline",
            size="sm",
            permission="sale.view_reports",
            default=True,
            refresh_on=FIGURE_EVENTS,
            kind="kpi",
            operation="sale.sale.today",
            map={"value": "tickets"},
            options={"format": "number", "tone": 2},
        ),
        Widget(
            key="last_7_days",
            title=_("Sales, last 7 days"),
            icon="ion:calendar-outline",
            size="lg",
            permission="sale.view_reports",
            refresh_on=FIGURE_EVENTS,
            kind="chart",
            operation="sale.sale.last_7_days",
            map={"label": "day", "value": "total"},
            options={"format": "currency"},
        ),
        # The sales list's own permission: whoever reads the sales sees the last ones charged.
        Widget(
            key="recent_activity",
            title=_("Recent activity"),
            icon="ion:time-outline",
            size="md",
            permission="sale.view_sale",
            refresh_on=SALE_EVENTS,
            kind="timeline",
            operation="sale.sale.list",
            params={"limit": 8, "sort": "created_at", "dir": "desc"},
            map={"title": "number", "description": "customer_name", "time": "created_at"},
        ),
    ]

    fiscal_archive_models = ("Sale", "SaleLine", "SalePayment", "Refund", "RefundLine", "RefundPayment")

    def fiscal_documents_kept(self) -> bool:
        """The platform asks (``base.tenancy.offboarding``) before it drops the database of a business that left: its
        sales here are documents to keep, so the database stays; they go to the fiscal archive first
        (``fiscal_archive_models``)."""
        from apps.sale import queries  # the models are not loaded yet when this module is

        return queries.sales.keeps_fiscal_documents()
