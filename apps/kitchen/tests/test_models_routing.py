"""Which station a product or a category goes to, and the rule the database itself keeps for it."""

from .conftest import HUB_DB, make_station, refused

pytestmark = HUB_DB


def test_a_product_and_a_category_go_to_one_station_at_most(product, category):
    from apps.kitchen.models.routing import CategoryRoute, ProductRoute

    grill, bar = make_station("Grill"), make_station("Bar")
    burger, mains = product("Burger"), category("Mains")
    ProductRoute.objects.create(product_id=burger.id, station=grill)
    CategoryRoute.objects.create(category_id=mains.id, station=grill)
    assert refused(
        lambda: ProductRoute.objects.create(product_id=burger.id, station=bar)
    )
    assert refused(
        lambda: CategoryRoute.objects.create(category_id=mains.id, station=bar)
    )
