"""Ninja routes of base: each route calls exactly one operation and holds no logic. One router per area, mounted in the
order of ``ROUTERS``, which is the order of their routes in the OpenAPI document."""

from ninja import Router

from . import access, apps, assistant, business, catalog_images, data, files, home, locations, people, system

ROUTERS = (
    home.router,
    apps.router,
    data.router,
    business.router,
    system.router,
    files.router,
    access.router,
    people.router,
    assistant.router,
    locations.router,
    catalog_images.router,
)

# The areas' routers name no tags: ninja adds a child router's tags to its parent's, and base's routes would carry two.
router = Router(tags=["base"])
for area in ROUTERS:
    router.add_router("", area)
