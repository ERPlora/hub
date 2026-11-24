"""What can be sold: which choices are offered, at which rate each is billed, and why a menu is not on the till."""

from django.utils.translation import gettext_lazy as _

from apps.combo.models import ChoiceOption, Combo
from apps.inventory.models import Unit
from apps.tax.models import TaxCategory

from .dish_options import TAKEAWAY_CATEGORY, takeaway_key

# Why a menu is not on the till (combo.combo.get «blockers»).
BLOCK_NOT_ON_SALE = _("It is not on sale.")
BLOCK_TAX_INACTIVE = _("Its tax category is not active in Taxes.")
BLOCK_NO_CHOICES = _("No course has a choice on offer.")
BLOCK_NO_CATALOG_PRICE = _(
    "Its choices cost nothing in the catalogue and are billed at different rates, so its VAT cannot be split."
)
BLOCK_GROUP_SHORT = _(
    "The course “%(group)s” has fewer choices on offer than it asks for."
)


def takeaway_targets() -> frozenset[str]:
    """The categories of ``TAKEAWAY_CATEGORY`` that Taxes has active: read once per operation."""
    targets = TaxCategory.objects.filter(key__in=TAKEAWAY_CATEGORY.values(), is_active=True)
    return frozenset(targets.values_list("key", flat=True))


def sold_by_unit(product) -> bool:
    """A portion: sold by units and priced per unit (the catalogue price is what one pick weighs)."""
    return product.unit == Unit.UNIT and product.pricing_unit == Unit.UNIT and product.price_quantity == 1


def premises_key(product) -> str | None:
    """The product's tax category, while Taxes has it active."""
    tax = product.tax_category
    return tax.key if tax and tax.is_active else None


def away_key(product, targets: frozenset[str]) -> str | None:
    """The category the product is billed at to take away; ``None`` when it has none."""
    return takeaway_key(premises_key(product), targets)


def offer_status(option: ChoiceOption, targets: frozenset[str]) -> str:  # noqa: PLR0911
    """offered, or why not: the product deleted, deactivated, sold out (INVENTORY-F29) or not sold by
    units in Inventory; with no rate to bill it at in a menu to take away; or sold out here."""
    product = option.product
    if product.is_deleted:
        return "product_deleted"
    if not product.is_active:
        return "product_inactive"
    if product.is_sold_out:
        return "product_sold_out"
    if not sold_by_unit(product):
        return "not_by_unit"
    if option.group.combo.supply_kind == Combo.SupplyKind.GOODS and away_key(product, targets) is None:
        return "untaxed"
    if not option.is_available:
        return "sold_out"
    return "offered"


def blockers(combo: Combo, targets: frozenset[str]) -> list[dict]:
    """Why the till does not offer ``combo`` (empty: it does). Reads its prefetched tree."""
    found: list[dict] = []
    if not combo.is_active:
        found.append(
            {
                "code": "combo.not_on_sale",
                "message": str(BLOCK_NOT_ON_SALE),
                "group_id": None,
            }
        )
    if combo.supply_kind == Combo.SupplyKind.SERVICE and not (
        combo.tax_category and combo.tax_category.is_active
    ):
        found.append(
            {
                "code": "combo.tax_category_inactive",
                "message": str(BLOCK_TAX_INACTIVE),
                "group_id": None,
            }
        )
    groups = list(combo.groups.all())
    offered = {
        group.id: [o for o in group.options.all() if offer_status(o, targets) == "offered"]
        for group in groups
    }
    if not any(offered.values()):
        found.append(
            {
                "code": "combo.no_choices",
                "message": str(BLOCK_NO_CHOICES),
                "group_id": None,
            }
        )
        return found
    for group in groups:
        count = len(offered[group.id])
        if (
            group.min_choices
            and count < group.min_choices
            and not (group.allow_repeat and count)
        ):
            message = str(BLOCK_GROUP_SHORT) % {"group": group.name}
            found.append(
                {"code": "combo.group_short", "message": message, "group_id": group.id}
            )
    on_offer = [option for options in offered.values() for option in options]
    if combo.supply_kind == Combo.SupplyKind.GOODS:
        rates = {away_key(option.product, targets) for option in on_offer}
        if len(rates) > 1 and not any(option.product.price for option in on_offer):
            found.append(
                {"code": "combo.no_catalog_price", "message": str(BLOCK_NO_CATALOG_PRICE), "group_id": None}
            )
    return found
