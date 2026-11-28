"""The routing as it stands today: which station cooks each product and each category."""

from dataclasses import dataclass
from uuid import UUID

from apps.kitchen.models.routing import CategoryRoute, ProductRoute
from apps.kitchen.models.stations import Station


@dataclass
class Routing:
    """Where a dish goes today: its product's station, else its category's (active stations only)."""

    products: dict[UUID, Station]
    categories: dict[UUID, Station]

    def station_for(
        self, product_id: UUID | None, category_id: UUID | None
    ) -> Station | None:
        if product_id is not None and product_id in self.products:
            return self.products[product_id]
        if category_id is not None:
            return self.categories.get(category_id)
        return None


def product_routes(**filters):
    """The routes of products still in the catalogue (a product deleted in Inventory no longer counts)."""
    return ProductRoute.objects.filter(product__is_deleted=False, **filters)


def category_routes(**filters):
    """The routes of categories still in the catalogue."""
    return CategoryRoute.objects.filter(category__is_deleted=False, **filters)


def routing() -> Routing:
    live = {"station__is_active": True, "station__is_deleted": False}
    return Routing(
        products={
            route.product_id: route.station
            for route in product_routes(**live).select_related("station")
        },
        categories={
            route.category_id: route.station
            for route in category_routes(**live).select_related("station")
        },
    )
