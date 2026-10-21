"""Ninja routes of the inventory app: each route calls exactly one operation and holds no logic.

No path parameters: a product or a category travels in the input (query string on GET, body on
POST), by its id or by its SKU or name, because a route takes one parameter, the operation's input.
The reactions to the Sales app's events (``inventory.stock.apply_sale``/``restore_sale``) have no
route: only the platform runs them.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.inventory import queries, services
from apps.inventory.schemas import (
    CategoryFiltersIn,
    CategoryImportIn,
    CategoryIn,
    CategoryListIn,
    CategoryPatchIn,
    CategoryRefIn,
    ConfigPatchIn,
    CountIn,
    ForSaleListIn,
    LowStockListIn,
    MovementListIn,
    ProductCategoryIn,
    ProductCategoryListIn,
    ProductFiltersIn,
    ProductImportIn,
    ProductIn,
    ProductListIn,
    ProductPatchIn,
    ProductRefIn,
    ProductSoldOutIn,
    ReceiveIn,
    UnitListIn,
    WriteOffIn,
)

router = Router(tags=["inventory"])


# Products


@bind(router, "inventory.product.list", "/inventory/products")
async def product_list(request, params: Query[ProductListIn]):
    return await run_operation(request, queries.list_products, params)


@bind(router, "inventory.product.get", "/inventory/products/detail")
async def product_detail(request, params: Query[ProductRefIn]):
    return await run_operation(request, queries.get_product, params)


@bind(router, "inventory.product.list_for_sale", "/inventory/products/for_sale")
async def product_list_for_sale(request, params: Query[ForSaleListIn]):
    return await run_operation(request, queries.list_for_sale, params)


@bind(router, "inventory.product.list_low_stock", "/inventory/products/low_stock")
async def product_list_low_stock(request, params: Query[LowStockListIn]):
    return await run_operation(request, queries.list_low_stock, params)


@bind(router, "inventory.product.export", "/inventory/products/export")
async def product_export(request, params: Query[ProductFiltersIn]):
    return await run_operation(request, queries.export_products, params)


@bind(router, "inventory.product.create", "/inventory/products", status=201)
async def product_create(request, data: ProductIn):
    return await run_operation(request, services.create_product, data)


@bind(router, "inventory.product.bulk_create", "/inventory/products/bulk_create")
async def product_bulk_create(request, data: ProductImportIn):
    return await run_operation(request, services.bulk_create_products, data)


@bind(router, "inventory.product.update", "/inventory/products/update")
async def product_update(request, data: ProductPatchIn):
    return await run_operation(request, services.update_product, data)


@bind(router, "inventory.product.delete", "/inventory/products/delete")
async def product_delete(request, data: ProductRefIn):
    return await run_operation(request, services.delete_product, data)


@bind(router, "inventory.product.set_sold_out", "/inventory/products/sold_out")
async def product_set_sold_out(request, data: ProductSoldOutIn):
    return await run_operation(request, services.set_sold_out, data)


@bind(router, "inventory.product.print_label", "/inventory/products/print_label")
async def product_print_label(request, data: ProductRefIn):
    return await run_operation(request, services.print_label, data)


# Products in categories


@bind(router, "inventory.product_category.list", "/inventory/product_categories")
async def product_category_list(request, params: Query[ProductCategoryListIn]):
    return await run_operation(request, queries.list_product_categories, params)


@bind(router, "inventory.product_category.add", "/inventory/product_categories/add")
async def product_category_add(request, data: ProductCategoryIn):
    return await run_operation(request, services.add_product_category, data)


@bind(router, "inventory.product_category.remove", "/inventory/product_categories/remove")
async def product_category_remove(request, data: ProductCategoryIn):
    return await run_operation(request, services.remove_product_category, data)


# Categories


@bind(router, "inventory.category.list", "/inventory/categories")
async def category_list(request, params: Query[CategoryListIn]):
    return await run_operation(request, queries.list_categories, params)


@bind(router, "inventory.category.export", "/inventory/categories/export")
async def category_export(request, params: Query[CategoryFiltersIn]):
    return await run_operation(request, queries.export_categories, params)


@bind(router, "inventory.category.create", "/inventory/categories", status=201)
async def category_create(request, data: CategoryIn):
    return await run_operation(request, services.create_category, data)


@bind(router, "inventory.category.bulk_create", "/inventory/categories/bulk_create")
async def category_bulk_create(request, data: CategoryImportIn):
    return await run_operation(request, services.bulk_create_categories, data)


@bind(router, "inventory.category.update", "/inventory/categories/update")
async def category_update(request, data: CategoryPatchIn):
    return await run_operation(request, services.update_category, data)


@bind(router, "inventory.category.delete", "/inventory/categories/delete")
async def category_delete(request, data: CategoryRefIn):
    return await run_operation(request, services.delete_category, data)


# Stock


@bind(router, "inventory.movement.list", "/inventory/movements")
async def movement_list(request, params: Query[MovementListIn]):
    return await run_operation(request, queries.list_movements, params)


@bind(router, "inventory.stock.get_summary", "/inventory/stock/summary")
async def stock_summary(request):
    return await run_operation(request, queries.get_summary)


@bind(router, "inventory.stock.receive", "/inventory/stock/receive")
async def stock_receive(request, data: ReceiveIn):
    return await run_operation(request, services.receive_stock, data)


@bind(router, "inventory.stock.count", "/inventory/stock/count")
async def stock_count(request, data: CountIn):
    return await run_operation(request, services.count_stock, data)


@bind(router, "inventory.stock.write_off", "/inventory/stock/write_off")
async def stock_write_off(request, data: WriteOffIn):
    return await run_operation(request, services.write_off_stock, data)


# Units and settings


@bind(router, "inventory.unit.list", "/inventory/units")
async def unit_list(request, params: Query[UnitListIn]):
    return await run_operation(request, queries.list_units, params)


@bind(router, "inventory.config.get", "/inventory/config")
async def config_get(request):
    return await run_operation(request, queries.get_config)


@bind(router, "inventory.config.update", "/inventory/config")
async def config_update(request, data: ConfigPatchIn):
    return await run_operation(request, services.update_config, data)
