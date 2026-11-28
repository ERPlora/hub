"""The tips app: the tip a customer leaves when paying, by card or in cash, kept apart from the sale with who it
belongs to, and entered in the open drawer as its own line (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, CheckoutStep, LiveAppConfig, Nav


class TipConfig(LiveAppConfig):
    name = "apps.tip"
    label = "tip"
    blueprint_stays = {
        "Settings": "settings",
        "Tip": "history",
    }
    kind = "app"
    verbose_name = _("Tips")
    icon = "ion:wallet-outline"
    category = Category.PEOPLE
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
    summary = _("Record the tips left by card or in cash, who each one belongs to, and see them apart in the drawer.")
    description = _(
        "Tips keeps the tip a customer leaves when paying, by card or in cash, with its sale and the person it belongs "
        "to: whoever served the check or did the service. A tip is no sale: it carries no VAT and never changes the "
        "ticket. A tip in cash enters the drawer and one by card shows apart in the cash register, a tip can be "
        "corrected or voided with its reason, and voiding or refunding a sale voids its tip by itself."
    )
    verticals = ["hair_salon", "restaurant"]
    # A tip goes with its sale and its payment method (Sales), enters the open drawer (Cash register) and belongs to a
    # member of the team (Staff).
    requires = ["sale", "cash_register", "staff"]
    default_auto_field = "django.db.models.BigAutoField"
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms): a «propina», a «bote» or a
    # «gratuity» is a tip (tip.tip).
    assistant_synonyms = (("propina", "propinas", "bote", "gratuity", "tip"),)
    assistant_settings = ("tip.settings.get",)
    # The «Tip» row of the charge sheet, which Sales mounts without knowing Tips (frontend/components/TipStep.vue).
    checkout = [CheckoutStep(key="tip", component="TipStep", permission="tip.add_tip")]
    # The report's views as its screen names them, so the assistant never says the code (tip.report.get).
    choices = {"by": (("person", _("By person")), ("shift", _("By shift")))}
    permissions = {
        "tip.view_tip": _("View tips (an employee, their own)"),
        "tip.add_tip": _("Record tips"),
        "tip.manage": _("Adjust and void tips"),
        "tip.manage_settings": _("Change the tip settings"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["tip.*"],
        "hub_admin": ["tip.*"],
        "hub_manager": ["tip.view_tip", "tip.add_tip", "tip.manage"],
        "hub_employee": ["tip.view_tip", "tip.add_tip"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with `icon =` as the
    # module's own icon. Whoever only records tips opens «My tips» alone; a manager reads the settings blocked.
    navigation = [
        Nav("tips", _("Tips"), "ion:wallet-outline", "/tip/tips", permission="tip.manage"),
        Nav("report", _("Report"), "ion:list-outline", "/tip/report", permission="tip.manage"),
        Nav("settings", _("Settings"), "ion:settings-outline", "/tip/settings", permission="tip.manage"),
        Nav("mine", _("My tips"), "ion:person-outline", "/tip/mine", permission="tip.view_tip"),
    ]
