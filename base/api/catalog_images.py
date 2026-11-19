"""Routes of the shared image library (``base.image_catalog``)."""

from live.ninja import bind, run_operation
from ninja import Query, Router

from base import queries
from base.schemas.catalog_images import CatalogImageRefIn, CatalogImageSearchIn

router = Router()


@bind(router, "base.catalog_image.search", "/catalog/images")
async def catalog_image_search(request, params: Query[CatalogImageSearchIn]):
    return await run_operation(request, queries.catalog_images.catalog_image_search, params)


@bind(router, "base.catalog_image.get", "/catalog/images/detail")
async def catalog_image_get(request, params: Query[CatalogImageRefIn]):
    return await run_operation(request, queries.catalog_images.catalog_image_get, params)
