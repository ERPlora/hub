"""The products: the catalog's list and one product, the sale catalog the till reads, what runs low, the
library's images for a product's photo, and whether a product tracks stock or can be sold."""

from functools import partial
from uuid import UUID

from django.db.models import BooleanField, Case, F, Prefetch, Q, Value, When
from live.context import OperationContext, Scope
from live.operations import operation

from apps.inventory.models import Product, ProductCategory, Settings
from apps.inventory.queries.reads import _bounds, _page, find_product
from apps.inventory.queries.settings import current_settings
from apps.inventory.schemas.fields import ProductRefIn
from apps.inventory.schemas.product_images import ProductImageSuggestIn, ProductImageSuggestOut
from apps.inventory.schemas.products import (
    ForSaleListIn,
    ProductFiltersIn,
    ProductListIn,
    ProductOut,
    ProductPage,
    SaleProductPage,
)
from apps.inventory.schemas.stock import LowStockListIn, LowStockPage
from base import images
from base.queries.catalog_images import image_suggestion, titled_search
from base.ordering import list_order_for

#: Products that cannot be sold for lack of a live tax category.
UNTAXED = Q(tax_category__isnull=True) | Q(tax_category__is_active=False)
#: On sale: what the till offers (INVENTORY-F27). A sold-out article (INVENTORY-F29) stays active, off the till.
ON_SALE = Q(is_active=True, is_sold_out=False)


def tracks_stock_expression(settings: Settings) -> Case:
    """Whether stock control applies to a product: never to a service; its own decision; else the business's."""
    return Case(
        When(product_type=Product.Type.SERVICE, then=Value(False)),
        When(track_stock__isnull=False, then=F("track_stock")),
        default=Value(settings.track_stock),
        output_field=BooleanField(),
    )


def tracks_stock(product: Product, settings: Settings) -> bool:
    """The same rule as ``tracks_stock_expression``, for a product already loaded."""
    if product.product_type == Product.Type.SERVICE:
        return False
    return settings.track_stock if product.track_stock is None else product.track_stock


def needs_tax_setup(product: Product) -> bool:
    """No tax category, or one that Taxes deactivated: it cannot be sold until it has one."""
    return product.tax_category is None or not product.tax_category.is_active


def load_product(product_id: UUID, scope: Scope) -> dict | None:
    """The live product of ``scope`` as a ``ProductOut``, or ``None``. Not an operation: services return it after a
    write."""
    product = _products(current_settings()).filter(pk=product_id).first()
    return None if product is None else _product_row(product, images.Urls(scope))


@operation(
    "inventory.product.list",
    kind="query",
    permission="inventory.view_product",
    input=ProductListIn,
    output=ProductPage,
    expose_api=True,
    ai={
        "description": "List the catalog's products with their current stock; needs_tax_setup marks the ones "
        "without a tax category, which cannot be sold, and is_sold_out the ones marked sold out. Filter by "
        "category to get one category's articles, by is_active=true to get what the till offers (add "
        "include_sold_out=true for every active product, sold out or not).",
        "asks": {
            "en": (
                "what products do I have?",
                "show me the catalog with their stock",
                "list all my products",
            ),
            "es": (
                "¿qué productos tengo?",
                "enséñame el catálogo con su stock",
                "lista todos mis productos",
            ),
        },
    },
)
def list_products(ctx: OperationContext, params: ProductListIn) -> dict:
    products = filter_products(_products(current_settings()), params)
    return _page(products, params, partial(_product_row, urls=images.Urls(ctx.scope)))


@operation(
    "inventory.product.get",
    kind="query",
    permission="inventory.view_product",
    input=ProductRefIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Get the full detail of one product, named by its id, its SKU or its name.",
        "asks": {
            "en": (
                "tell me everything about the coffee product",
                "show the detail of the croissant",
            ),
            "es": (
                "dime todo del producto café",
                "enséñame la ficha del cruasán",
            ),
        },
    },
)
def get_product(ctx: OperationContext, data: ProductRefIn) -> dict:
    return _product_row(
        find_product(data.id, data.product, rows=_products(current_settings())), images.Urls(ctx.scope)
    )


@operation(
    "inventory.product.suggest_image",
    kind="query",
    permission="inventory.view_product",
    input=ProductImageSuggestIn,
    output=ProductImageSuggestOut,
    expose_api=True,
    ai={
        "description": "Propose images of ERPlora's shared image library for a product's photo («ponle foto al café "
        "con leche»), the product named by its id, SKU or name: " + image_suggestion("inventory.product.set_image"),
        "asks": {
            "en": (
                "which library images could fit the latte?",
                "suggest an image for the croissant",
            ),
            "es": (
                "¿qué imagen le iría al café con leche?",
                "propón una imagen para el cruasán",
            ),
        },
    },
)
def suggest_image(ctx: OperationContext, data: ProductImageSuggestIn) -> dict:
    """INVENTORY-F30: the library searched by the product's name in either of its languages, titled in the person's."""
    product = find_product(data.id, data.product)
    return {
        "product_id": product.id,
        "query": product.name,
        "rows": titled_search(ctx, product.name)[: data.limit],
    }


@operation(
    "inventory.product.list_for_sale",
    kind="query",
    permission="inventory.view_product",
    input=ForSaleListIn,
    output=SaleProductPage,
    expose_api=True,
    ai={
        "description": "Sale catalog: the products on sale (active, not sold out) with what prices a sale line "
        "(price, cost, tax category, units) and whether a sale lowers their stock; never their stock.",
        "asks": {
            "en": (
                "what can I sell right now?",
                "list the products on sale with their prices",
            ),
            "es": (
                "¿qué puedo vender ahora mismo?",
                "lista los productos a la venta con sus precios",
            ),
        },
    },
)
def list_for_sale(ctx: OperationContext, params: ForSaleListIn) -> dict:
    products = (
        Product.objects.filter(ON_SALE, is_deleted=False)
        .select_related("tax_category")
        .annotate(tracks=tracks_stock_expression(current_settings()))
    )
    if params.search:
        products = products.filter(
            Q(name__icontains=params.search) | Q(sku__icontains=params.search)
        )
    return _page(products.order_by("name", "id"), params, partial(_sale_row, urls=images.Urls(ctx.scope)))


@operation(
    "inventory.product.list_low_stock",
    kind="query",
    permission="inventory.view_product",
    input=LowStockListIn,
    output=LowStockPage,
    expose_api=True,
    ai={
        "description": "List the active articles with stock control at or under their low-stock threshold, the one with "
        "less first. A balance at zero or below does not take an article off the till: the till still offers it, and "
        "only one marked sold out (is_sold_out) is not offered.",
        "asks": {
            "en": (
                "what is running low?",
                "which products are almost out of stock?",
                "which products are below their minimum stock?",
            ),
            "es": (
                "¿qué me queda poco?",
                "¿qué productos están a punto de agotarse?",
                "¿qué productos están por debajo del stock mínimo?",
            ),
        },
    },
)
def list_low_stock(ctx: OperationContext, params: LowStockListIn) -> dict:
    products = (
        Product.objects.filter(is_deleted=False, is_active=True)
        .annotate(tracks=tracks_stock_expression(current_settings()))
        .filter(tracks=True, stock__lte=F("low_stock_threshold"))
    )
    if params.search:
        products = products.filter(
            Q(name__icontains=params.search) | Q(sku__icontains=params.search)
        )
    if params.sku:
        products = products.filter(sku=params.sku)
    products = products.filter(
        **_bounds(stock__gte=params.stock_min, stock__lte=params.stock_max)
    )
    fields = (
        "id",
        "name",
        "sku",
        "stock",
        "low_stock_threshold",
        "is_sold_out",
        "unit",
        "price_quantity",
        "pricing_unit",
    )
    return _page(
        products.order_by(*list_order_for(params.sort)),
        params,
        lambda product: {field: getattr(product, field) for field in fields},
    )


def filter_products(products, params: ProductFiltersIn):  # noqa: C901
    """The product list's search, filters and order (the export takes the same)."""
    if params.search:
        products = products.filter(
            Q(name__icontains=params.search) | Q(sku__icontains=params.search)
        )
    if params.name:
        products = products.filter(name__icontains=params.name)
    if params.sku:
        products = products.filter(sku__icontains=params.sku)
    products = products.filter(
        **_bounds(
            price__gte=params.price_min,
            price__lte=params.price_max,
            stock__gte=params.stock_min,
            stock__lte=params.stock_max,
            tracks=params.tracks_stock,
            product_type=params.product_type,
        )
    )
    if params.is_active is not None:
        # The till asks for what is on sale; a screen that configures, for the switch alone.
        active = Q(is_active=True) if params.include_sold_out else ON_SALE
        products = products.filter(active if params.is_active else ~active)
    if params.needs_tax_setup is not None:
        products = products.filter(UNTAXED if params.needs_tax_setup else ~UNTAXED)
    if params.status == "needs_tax_setup":
        products = products.filter(UNTAXED)
    elif params.status == "sold_out":
        products = products.filter(is_sold_out=True)
    elif params.status is not None:
        products = products.filter(~UNTAXED, is_active=params.status == "active")
    links = ProductCategory.objects.filter(category__is_deleted=False)
    if params.category_id:
        products = products.filter(
            pk__in=links.filter(category_id=params.category_id).values("product_id")
        )
    if params.category:
        said = Q(category__name__iexact=params.category) | Q(
            category__slug__iexact=params.category
        )
        products = products.filter(pk__in=links.filter(said).values("product_id"))
    return products.order_by(*list_order_for(params.sort))


def _products(settings: Settings):
    live_links = ProductCategory.objects.filter(category__is_deleted=False).order_by(
        "category__name", "category_id"
    )
    return (
        Product.objects.filter(is_deleted=False)
        .select_related("tax_category")
        .annotate(tracks=tracks_stock_expression(settings))
        .prefetch_related(
            Prefetch("category_links", queryset=live_links, to_attr="live_links")
        )
    )


def _product_row(product: Product, urls: images.Urls) -> dict:
    """What the till reads of the product (``_sale_row``) and what only the back office does."""
    fields = (
        "ean13",
        "stock",
        "low_stock_threshold",
        "track_stock",
        "is_active",
        "is_sold_out",
        "created_at",
        "updated_at",
    )
    return {
        **_sale_row(product, urls),
        **{field: getattr(product, field) for field in fields},
        "category_ids": [link.category_id for link in product.live_links],
    }


def _sale_row(product: Product, urls: images.Urls) -> dict:
    fields = (
        "id",
        "name",
        "description",
        "sku",
        "product_type",
        "price",
        "cost",
        "tax_category_id",
        "unit",
        "price_quantity",
        "pricing_unit",
        "allergens",
    )
    return {
        **{field: getattr(product, field) for field in fields},
        "tax_category_key": product.tax_category.key if product.tax_category else None,
        "needs_tax_setup": needs_tax_setup(product),
        "tracks_stock": product.tracks,
        "image": product.image,
        "image_url": urls(product.image),
    }
