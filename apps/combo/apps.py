"""The combo app: menus and combos sold at a closed price, with courses to pick from Inventory's
products, a supplement per choice and the VAT split a sale applies (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class ComboConfig(LiveAppConfig):
    name = "apps.combo"
    label = "combo"
    kind = "app"
    verbose_name = _("Menus and combos")
    # Registered in the shell (ION_ICONS); `restaurant-outline` waits in UI-REQUESTS.md.
    icon = "ion:layers-outline"
    category = Category.CATALOG
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
    summary = _(
        "Set menus and combos at a closed price, with courses, supplements and the right VAT."
    )
    description = _(
        "Menus and combos sells the menu of the day, the kids' menu or a sandwich with a drink at one "
        "closed price: each menu has its courses, each course the products the customer picks from, "
        "with a supplement when a choice costs more. Mark a dish as sold out, reorder courses and "
        "choices, and the till charges the menu with the right VAT: one line when it is eaten in, split "
        "per dish when it is sold to take away, while the stock of every dish goes down."
    )
    verticals = ["restaurant"]
    # A choice is a product of Inventory; a menu eaten in has a tax category of Taxes.
    requires = ["inventory", "tax"]
    # The menus' own photos (COMBO-F14, base.images): served by /p/media/ to the hub's sessions only.
    members_media = ["combo/combos/"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = ["combo.view", "combo.manage"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["combo.*"],
        "hub_admin": ["combo.*"],
        "hub_manager": ["combo.*"],
        "hub_employee": ["combo.view"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. One entry, no tabbar.
    navigation = [Nav("menus", _("Menus"), "ion:layers-outline", "/combo/menus")]

    def recoverable_from_copy(self) -> list:
        """What a separate copy of the business gives back when ERPlora's staff recovers from it (BASE-F114): each
        choice of a product that the business no longer offers in its course, offered again by ``combo.option.create``,
        the menu builder's own. It goes after Inventory, so a deleted product is back before its choices."""
        from apps.combo import queries  # the models are not loaded yet when this module is
        from base.recovery import Recoverable

        return [
            Recoverable(
                label=_("Menu choices of products"),
                reads_since="0001_initial",
                read=queries.options_in_copy,
                missing=queries.options_not_in_business,
                create="combo.option.create",
            )
        ]
