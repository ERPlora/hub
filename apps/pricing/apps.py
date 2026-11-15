"""The pricing app: price lists per customer group, with quantity breaks and dates, the automatic
discount rules of a line, and the price a line takes (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class PricingConfig(LiveAppConfig):
    name = "apps.pricing"
    label = "pricing"
    kind = "app"
    verbose_name = _("Price Lists")
    # Registered in the shell (ION_ICONS).
    icon = "ion:pricetag"
    category = Category.CATALOG
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
    summary = _("Price lists per customer group, with dates and quantity breaks, and automatic discounts.")
    description = _(
        "Price Lists keeps other prices for your products and services: a list for wholesale customers, "
        "one for your VIP group, a summer list between two dates, or a lower price from ten units on. "
        "It also keeps automatic discount rules, such as 10 % on a category, an amount off each unit, "
        "buy two and get one free, or a discount by quantity. Given a product or a service, a customer, "
        "a quantity and a day, it says which price applies, from which list, which rule takes how much "
        "off and what is left: always the lowest price and the best single discount for the customer."
    )
    # A salon prices its VIP members, a restaurant its wholesale and happy customers.
    verticals = ["hair_salon", "restaurant"]
    # A price and a rule point at Inventory's products and categories and at Customers' groups;
    # Services is read by the name of its operations (it is no requirement: WORKBOOK).
    requires = ["inventory", "customer"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = ["pricing.view", "pricing.manage"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). Viewing includes
    # asking for the price of a line.
    role_permissions = {
        "hub_owner": ["pricing.*"],
        "hub_admin": ["pricing.*"],
        "hub_manager": ["pricing.*"],
        "hub_employee": ["pricing.view"],
    }
    # Positional (id, label, icon, path): scripts/app-icons.mjs reads every line starting with
    # `icon =` as the module's own icon. One entry: lists and rules on one screen.
    navigation = [
        Nav("lists", _("Price Lists"), "ion:pricetag", "/pricing/lists"),
    ]

    def recoverable_from_copy(self) -> list:
        """What a separate copy of the business gives back when ERPlora's staff recovers from it (BASE-F114): each price
        the business no longer has, put back by ``pricing.price_item.add``, the list detail's own, where the business
        has not priced that place again. It goes after Inventory, so a deleted product is back before its prices."""
        from apps.pricing import queries  # the models are not loaded yet when this module is
        from base.recovery import Recoverable

        return [
            Recoverable(
                label=_("Price list prices"),
                reads_since="0001_initial",
                read=queries.prices_in_copy,
                missing=queries.prices_not_in_business,
                create="pricing.price_item.add",
            )
        ]
