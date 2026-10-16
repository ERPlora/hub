"""The modifier app: groups of choices that go with a dish (sauces, doneness, extras), their options with
a price supplement, and the products or categories of Inventory each group is linked to (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class ModifierConfig(LiveAppConfig):
    name = "apps.modifier"
    label = "modifier"
    kind = "app"
    verbose_name = _("Modifiers")
    # The old `options-outline` is a pair of sliders: Lucide's, registered in the shell, is the same drawing.
    icon = "lucide:sliders-horizontal"
    category = Category.CATALOG
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "Supplements and choices of a dish: sauces, doneness, extras, each with its price."
    )
    description = _(
        "Modifiers keeps the choices that go with what you sell: the doneness of the meat, an extra of "
        "cheese, the size, «no onion». Each group says how many options must be chosen and whether one "
        "can be repeated; each option carries its supplement, more, less or free, and can come chosen by "
        "default. One group serves many products and whole categories, and the till asks for it, charges "
        "the supplement at the catalog price and sends it to the kitchen with its own name."
    )
    # A restaurant's menu asks for doneness and extras; the hair salon's template does not carry it.
    verticals = ["restaurant"]
    # A link points at a product or a category of Inventory; an option at a tax category of Taxes.
    requires = ["inventory", "tax"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = ["modifier.view", "modifier.manage"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old cashier
    # role is an employee: it reads the groups of a product and has its picks valued.
    role_permissions = {
        "hub_owner": ["modifier.*"],
        "hub_admin": ["modifier.*"],
        "hub_manager": ["modifier.*"],
        "hub_employee": ["modifier.view"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon, and a keyword split over lines would look like one.
    navigation = [
        Nav("groups", _("Modifiers"), "lucide:sliders-horizontal", "/modifier/groups")
    ]
