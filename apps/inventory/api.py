"""Ninja routes of the inventory app: each route calls exactly one operation and holds no logic.

No path parameters: a product or a category travels in the input (query string on GET, body on
POST), by its id or by its SKU or name, because a route takes one parameter, the operation's input.
The reactions to the Sales app's events (``inventory.stock.apply_sale``/``restore_sale``) have no
route: only the platform runs them.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router
from ninja.decorators import decorate_view

from apps.inventory import queries, services
from apps.inventory.schemas.categories import CategoryFiltersIn, CategoryIn, CategoryListIn, CategoryPatchIn
from apps.inventory.schemas.fields import CategoryRefIn, ProductRefIn
from apps.inventory.schemas.imports import CategoryImportIn, ProductImportIn
from apps.inventory.schemas.movements import MovementListIn
from apps.inventory.schemas.product_categories import ProductCategoryIn, ProductCategoryListIn
from apps.inventory.schemas.product_images import ProductImageIn, ProductImageSuggestIn, ProductImageUploadIn
from apps.inventory.schemas.products import (
    ForSaleListIn,
    ProductFiltersIn,
    ProductIn,
    ProductListIn,
    ProductPatchIn,
    ProductSoldOutIn,
)
from apps.inventory.schemas.settings import ConfigPatchIn
from apps.inventory.schemas.stock import CountIn, LowStockListIn, ReceiveIn, WriteOffIn
from apps.inventory.schemas.units import UnitListIn
from base.request_body import accept_body_up_to

router = Router(tags=["inventory"])

#: A photo's body: 2 MB of photo in base64 (2 796 204 characters) and the JSON around it.
MAX_PHOTO_BODY = 2_900_000


# Products


@bind(router, "inventory.product.list", "/inventory/products")
async def product_list(request, params: Query[ProductListIn]):
    return await run_operation(request, queries.products.list_products, params)


@bind(router, "inventory.product.get", "/inventory/products/detail")
async def product_detail(request, params: Query[ProductRefIn]):
    return await run_operation(request, queries.products.get_product, params)


@bind(router, "inventory.product.list_for_sale", "/inventory/products/for_sale")
async def product_list_for_sale(request, params: Query[ForSaleListIn]):
    return await run_operation(request, queries.products.list_for_sale, params)


@bind(router, "inventory.product.list_low_stock", "/inventory/products/low_stock")
async def product_list_low_stock(request, params: Query[LowStockListIn]):
    return await run_operation(request, queries.products.list_low_stock, params)


@bind(router, "inventory.product.export", "/inventory/products/export")
async def product_export(request, params: Query[ProductFiltersIn]):
    return await run_operation(request, queries.exports.export_products, params)


@bind(router, "inventory.product.create", "/inventory/products", status=201)
async def product_create(request, data: ProductIn):
    return await run_operation(request, services.products.create_product, data)


@bind(router, "inventory.product.bulk_create", "/inventory/products/bulk_create")
async def product_bulk_create(request, data: ProductImportIn):
    return await run_operation(request, services.imports.bulk_create_products, data)


@bind(router, "inventory.product.update", "/inventory/products/update")
async def product_update(request, data: ProductPatchIn):
    return await run_operation(request, services.products.update_product, data)


@bind(router, "inventory.product.delete", "/inventory/products/delete")
async def product_delete(request, data: ProductRefIn):
    return await run_operation(request, services.products.delete_product, data)


@bind(router, "inventory.product.set_sold_out", "/inventory/products/sold_out")
async def product_set_sold_out(request, data: ProductSoldOutIn):
    return await run_operation(request, services.products.set_sold_out, data)


@bind(router, "inventory.product.print_label", "/inventory/products/print_label")
async def product_print_label(request, data: ProductRefIn):
    return await run_operation(request, services.labels.print_label, data)


# Products in categories


@bind(router, "inventory.product_category.list", "/inventory/product_categories")
async def product_category_list(request, params: Query[ProductCategoryListIn]):
    return await run_operation(request, queries.categories.list_product_categories, params)


@bind(router, "inventory.product_category.add", "/inventory/product_categories/add")
async def product_category_add(request, data: ProductCategoryIn):
    return await run_operation(request, services.product_categories.add_product_category, data)


@bind(router, "inventory.product_category.remove", "/inventory/product_categories/remove")
async def product_category_remove(request, data: ProductCategoryIn):
    return await run_operation(request, services.product_categories.remove_product_category, data)


# Categories


@bind(router, "inventory.category.list", "/inventory/categories")
async def category_list(request, params: Query[CategoryListIn]):
    return await run_operation(request, queries.categories.list_categories, params)


@bind(router, "inventory.category.export", "/inventory/categories/export")
async def category_export(request, params: Query[CategoryFiltersIn]):
    return await run_operation(request, queries.exports.export_categories, params)


@bind(router, "inventory.category.create", "/inventory/categories", status=201)
async def category_create(request, data: CategoryIn):
    return await run_operation(request, services.categories.create_category, data)


@bind(router, "inventory.category.bulk_create", "/inventory/categories/bulk_create")
async def category_bulk_create(request, data: CategoryImportIn):
    return await run_operation(request, services.imports.bulk_create_categories, data)


@bind(router, "inventory.category.update", "/inventory/categories/update")
async def category_update(request, data: CategoryPatchIn):
    return await run_operation(request, services.categories.update_category, data)


@bind(router, "inventory.category.delete", "/inventory/categories/delete")
async def category_delete(request, data: CategoryRefIn):
    return await run_operation(request, services.categories.delete_category, data)


# Stock


@bind(router, "inventory.movement.list", "/inventory/movements")
async def movement_list(request, params: Query[MovementListIn]):
    return await run_operation(request, queries.movements.list_movements, params)


@bind(router, "inventory.stock.get_summary", "/inventory/stock/summary")
async def stock_summary(request):
    return await run_operation(request, queries.stock.get_summary)


@bind(router, "inventory.stock.receive", "/inventory/stock/receive")
async def stock_receive(request, data: ReceiveIn):
    return await run_operation(request, services.stock.receive_stock, data)


@bind(router, "inventory.stock.count", "/inventory/stock/count")
async def stock_count(request, data: CountIn):
    return await run_operation(request, services.stock.count_stock, data)


@bind(router, "inventory.stock.write_off", "/inventory/stock/write_off")
async def stock_write_off(request, data: WriteOffIn):
    return await run_operation(request, services.stock.write_off_stock, data)


# Units and settings


@bind(router, "inventory.unit.list", "/inventory/units")
async def unit_list(request, params: Query[UnitListIn]):
    return await run_operation(request, queries.units.list_units, params)


@bind(router, "inventory.config.get", "/inventory/config")
async def config_get(request):
    return await run_operation(request, queries.settings.get_config)


@bind(router, "inventory.config.update", "/inventory/config")
async def config_update(request, data: ConfigPatchIn):
    return await run_operation(request, services.settings.update_config, data)


# The product's image (base.images)


@bind(router, "inventory.product.set_image", "/inventory/products/image")
async def product_image_set(request, data: ProductImageIn):
    return await run_operation(request, services.product_images.set_image, data)


@bind(router, "inventory.product.upload_image", "/inventory/products/image/upload")
@decorate_view(accept_body_up_to(MAX_PHOTO_BODY))
async def product_image_upload(request, data: ProductImageUploadIn):
    return await run_operation(request, services.product_images.upload_image, data)


@bind(router, "inventory.product.suggest_image", "/inventory/products/image/suggest")
async def product_image_suggest(request, params: Query[ProductImageSuggestIn]):
    return await run_operation(request, queries.products.suggest_image, params)
