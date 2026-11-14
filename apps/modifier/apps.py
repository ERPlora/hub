"""The modifier app: groups of choices that go with a dish (sauces, doneness, extras), their options with
a price supplement, and the products or categories of Inventory each group is linked to (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class ModifierConfig(LiveAppConfig):
    name = "apps.modifier"
    label = "modifier"
    kind = "app"
    verbose_name = _("Modifiers")
    # A pair of sliders, as `options-outline`; Lucide's is registered in the shell.
    icon = "lucide:sliders-horizontal"
    category = Category.CATALOG
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The cashier is an
    # employee: it reads the groups of a product and has its picks valued.
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

    def recoverable_from_copy(self) -> list:
        """What a separate copy of the business gives back when ERPlora's staff recovers from it (BASE-F114): each group
        the business no longer has, made again with its options by ``modifier.group.recover``; then each group hung from
        a category, then each hung from a product, that the business no longer hangs there, hung again by
        ``modifier.link.attach``, the group sheet's own, each counted apart. It goes after Inventory, so a deleted
        category or product is back before its groups."""
        from apps.modifier import queries  # the models are not loaded yet when this module is
        from base.recovery import Recoverable

        return [
            Recoverable(
                label=_("Modifier groups"),
                reads_since="0001_initial",
                read=queries.groups_in_copy,
                missing=queries.groups_not_in_business,
                create="modifier.group.recover",
            ),
            Recoverable(
                label=_("Modifier groups of categories"),
                reads_since="0001_initial",
                read=queries.category_links_in_copy,
                missing=queries.category_links_not_in_business,
                create="modifier.link.attach",
            ),
            Recoverable(
                label=_("Modifier groups of products"),
                reads_since="0001_initial",
                read=queries.links_in_copy,
                missing=queries.links_not_in_business,
                create="modifier.link.attach",
            )
        ]
