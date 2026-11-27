"""The pricing app: price lists per customer group, with quantity breaks and dates, the automatic
discount rules of a line, and the price a line takes (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, Help, LiveAppConfig, Nav


class PricingConfig(LiveAppConfig):
    name = "apps.pricing"
    label = "pricing"
    blueprint_stays = {
        "PriceList": "pending",
        "PriceItem": "pending",
        "DiscountRule": "pending",
    }
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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms): the discount of something («el
    # descuento de los cafés», «the discount on coffees») is the rule that takes it off, as «la regla de descuento de
    # los cafés» is; a discount said by how much it takes off («un descuento de 5 €», «a 10 % discount on the wine»)
    # names no rule. What the business charges for something at an amount («la caña la cobro a 2,50») is its price, not
    # what it charges to a table («se la cobro a la mesa 4»). A phrase matches whole words in a row and an amount is read
    # by its whole part («2,50» as «2»), so each amount up to 999 is a phrase of its own. «I charge» is not one, because
    # it also charges a check («should I charge again?»).
    assistant_synonyms = (
        (
            "regla", "rule", "el descuento de", "los descuentos de", "el descuento en", "los descuentos en",
            "the discount on", "the discounts on",
        ),
        ("precio", "price", *(f"{charged} a {amount}" for charged in ("cobro", "cobramos") for amount in range(1000))),
    )
    permissions = {
        "pricing.view": _("View price lists, prices and rules"),
        "pricing.manage": _("Create, change, deactivate and reactivate price lists, and pick the default one"),
    }
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
        Nav("lists", _("Price Lists"), "ion:pricetag", "/pricing/lists", permission="pricing.manage"),
    ]
    help = Help(
        videos={"es": "cL0GmPik7GY", "en": "8fbHffF_tRg"},
        flow_videos={
            "PRICING-F02": {"es": ["PcXCOovdV4g"], "en": ["KSGMcNbYdU4"]},
            "PRICING-F03": {"es": ["PcXCOovdV4g"], "en": ["KSGMcNbYdU4"]},
            "PRICING-F04": {"es": ["-pxJmxIpO7c"], "en": ["0AuaTApG1TM"]},
            "PRICING-F05": {"es": ["PcXCOovdV4g"], "en": ["KSGMcNbYdU4"]},
            "PRICING-F06": {"es": ["hsA1bvxJvAw"], "en": ["Hf_-Vn1_dOk"]},
            "PRICING-F07": {"es": ["hsA1bvxJvAw"], "en": ["Hf_-Vn1_dOk"]},
            "PRICING-F08": {"es": ["hsA1bvxJvAw"], "en": ["Hf_-Vn1_dOk"]},
            "PRICING-F09": {"es": ["R4voL1_MuGQ"], "en": ["pWjQIHi7V34"]},
            "PRICING-F10": {"es": ["R4voL1_MuGQ"], "en": ["pWjQIHi7V34"]},
            "PRICING-F11": {"es": ["R4voL1_MuGQ"], "en": ["pWjQIHi7V34"]},
            "PRICING-F12": {"es": ["R4voL1_MuGQ"], "en": ["pWjQIHi7V34"]},
        },
    )

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
                read=queries.recovery.prices_in_copy,
                missing=queries.recovery.prices_not_in_business,
                create="pricing.price_item.add",
            )
        ]
