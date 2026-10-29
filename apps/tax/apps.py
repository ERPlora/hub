"""The tax app: fiscal categories, the rules that give each one its rate by country, region and date,
and the aliases the CSV importer of inventory recognises (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav, SetupCheck, SetupStep

from apps.tax.events import RULE_IN_FORCE_EVENTS


class TaxConfig(LiveAppConfig):
    name = "apps.tax"
    label = "tax"
    kind = "app"
    verbose_name = _("Taxes")
    icon = "ion:calculator-outline"
    category = Category.SALES
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Tax categories and the VAT rate of each one, by country, region and date."
    )
    description = _(
        "Taxes keeps the tax categories your products and services point to, and the rules that give "
        "each one its rate in your country or region and between two dates: VAT, IGIC or IPSI, exempt "
        "or not subject operations and the equivalence surcharge. It comes with the Spanish rates "
        "ready, lets you schedule a rate change ahead, never lets two rates apply on the same day, "
        "and is what the till and the invoices use to charge and declare each line."
    )
    # Every hair salon and every restaurant turns it on at sign-up: no sale is priced without it.
    verticals = ["hair_salon", "restaurant"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = ["tax.view", "tax.manage"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). Viewing
    # includes calculating; the old cashier role is an employee.
    role_permissions = {
        "hub_owner": ["tax.*"],
        "hub_admin": ["tax.*"],
        "hub_manager": ["tax.*"],
        "hub_employee": ["tax.view"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon, and a keyword split over lines would look like one.
    # The same icons as the tabbar (frontend/tabs.ts): the old menu's.
    navigation = [
        Nav("categories", _("Categories"), "ion:pricetags-outline", "/tax/categories"),
        Nav("rules", _("Rules"), "ion:receipt-outline", "/tax/rules"),
        Nav("aliases", _("Aliases"), "ion:swap-horizontal-outline", "/tax/aliases"),
        # The business's tax region (TAX-F11).
        Nav("settings", _("Settings"), "ion:settings-outline", "/tax/settings"),
    ]
    # The Home's hook (PLAN-HUB round 2026-10-21): the old module's own item «Your taxes» (module.json `setup`,
    # taxes#19), order 20 and important, done once one active root rule of any country applies today (TAX-F17: the
    # query and the words of the notice of the tax screens), for whoever manages taxes, leading to the rules.
    # Refreshed on what changes the rules in force. The old module declared no panel and no bell row.
    setup = [
        SetupStep(
            key="rules",
            operation="tax.rule.status",
            configured_when=[SetupCheck(field="configured", truthy=True)],
            title=_("Your taxes"),
            description=_("Set up the VAT rates of the country you sell in so the till can price a sale."),
            icon="ion:receipt-outline",
            route="/tax/rules",
            permission="tax.manage",
            order=20,
            required=True,
            refresh_on=RULE_IN_FORCE_EVENTS,
        )
    ]
