"""Read operations of the inventory app (``READ ONLY``): lists, the product, the sale catalog, the panel and exports.

Every list pages (``limit`` ≤ 100) with ``id`` as the tie-break, so pages never overlap, and has a
``search``. Deleted products and categories are out of every list; the ledger keeps showing their
movements. ``find_product`` and ``find_category`` resolve how a person names them (assistant, voice).
"""

import csv
import io
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from babel import Locale
from babel.numbers import format_currency, format_decimal, get_decimal_symbol
from django.conf import settings
from django.core.exceptions import EmptyResultSet
from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Prefetch,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Cast, Coalesce, NullIf
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.inventory.models import (
    UNIT_SPECS,
    Category,
    Product,
    ProductCategory,
    SaleStock,
    Settings,
    StockMovement,
    Unit,
)
from apps.inventory.schemas import (
    CategoryFiltersIn,
    CategoryListIn,
    CategoryPage,
    ConfigGetIn,
    ConfigOut,
    ExportOut,
    ForSaleListIn,
    LowStockListIn,
    LowStockPage,
    MovementListIn,
    MovementPage,
    ProductCategoryListIn,
    ProductCategoryPage,
    ProductFiltersIn,
    ProductListIn,
    ProductOut,
    ProductPage,
    ProductRefIn,
    SaleProductPage,
    SummaryIn,
    SummaryOut,
    UnitListIn,
    UnitPage,
)

PRODUCT_NOT_FOUND = _("This product does not exist in this hub.")
CATEGORY_NOT_FOUND = _("This category no longer exists.")
PRODUCT_AMBIGUOUS = _("“%(said)s” matches several products: %(names)s. Say which one.")
CATEGORY_AMBIGUOUS = _(
    "“%(said)s” matches several categories: %(names)s. Say which one."
)
PRODUCTS_FILENAME = _("inventory-products.csv")
CATEGORIES_FILENAME = _("inventory-categories.csv")
# The export's headers are the ones the import recognizes.
PRODUCT_HEADERS = (
    _("Name"),
    _("SKU"),
    _("Price"),
    _("Cost"),
    _("Stock"),
    _("Threshold"),
    _("EAN-13"),
    _("Description"),
    _("Unit"),
    _("Tax category"),
    _("Active"),
)
CATEGORY_HEADERS = (_("Name"), _("Slug"), _("Products"))
YES, NO = _("Yes"), _("No")
CSV_CONTENT_TYPE = "text/csv"
# Excel reads a CSV as UTF-8 only with it.
BOM = "\ufeff"
# The Hub has no currency setting yet: every ERPlora business invoices in euros (VeriFactu, Spain).
CURRENCY = "EUR"
#: What a spreadsheet runs as a formula at the start of a cell (=HYPERLINK, @SUM…): a text cell that
#: starts so gets an apostrophe in front, which the import takes back (services.EXPORT_GUARD).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


#: Products that cannot be sold for lack of a live tax category.
UNTAXED = Q(tax_category__isnull=True) | Q(tax_category__is_active=False)
#: On sale: what the till offers (INVENTORY-F27). A sold-out article (INVENTORY-F29) stays active, off the till.
ON_SALE = Q(is_active=True, is_sold_out=False)


# Shared by services.py, inside the command's own transaction


def current_settings() -> Settings:
    """The business's settings; the factory ones (unsaved) if they were never saved."""
    return Settings.objects.first() or Settings()


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


def load_product(product_id: UUID) -> dict | None:
    """The live product as a ``ProductOut``, or ``None``. Not an operation: services return it after a write."""
    product = _products(current_settings()).filter(pk=product_id).first()
    return None if product is None else _product_row(product)


def load_category(category_id: UUID) -> dict | None:
    category = _categories().filter(pk=category_id).first()
    return None if category is None else _category_row(category)


def find_product(
    product_id: UUID | None, said: str | None, *, lock: bool = False, rows=None
) -> Product:
    """The live product named by its id, or by its SKU or name as a person says it.

    By text: the SKU (ignoring case), else the exact name, else the only name that contains it.
    ``NotFound`` when none matches; 409 ``inventory.product_ambiguous`` when several do.
    The product comes from ``rows`` when given (e.g. ready for its row): one read, so a deletion committed
    meanwhile is either not seen yet or not found, never a row that vanished between two reads.
    """
    products = Product.objects.filter(is_deleted=False)
    if product_id is None:
        candidates = _first_match(
            products,
            (Q(sku__iexact=said), Q(name__iexact=said), Q(name__icontains=said)),
        )
        if len(candidates) > 1:
            names = ", ".join(
                f"{product.name} ({product.sku})" for product in candidates[:5]
            )
            raise Conflict(
                str(PRODUCT_AMBIGUOUS) % {"said": said, "names": names},
                code="inventory.product_ambiguous",
            )
        product_id = candidates[0].pk if candidates else None
    found = (products if rows is None else rows).filter(pk=product_id)
    product = (found.select_for_update() if lock else found).first()
    if product is None:
        raise NotFound(str(PRODUCT_NOT_FOUND))
    return product


def find_category(
    category_id: UUID | None,
    said: str | None,
    *,
    lock: bool = False,
    hold: bool = False,
) -> Category:
    """The live category named by its id, or by its name or slug: exact first, else the only one that contains it.

    ``lock`` takes it to change it; ``hold`` takes it to name it (a product put in it, see ``held``).
    """
    categories = Category.objects.filter(is_deleted=False)
    if category_id is None:
        candidates = _first_match(
            categories,
            (Q(slug__iexact=said) | Q(name__iexact=said), Q(name__icontains=said)),
        )
        if len(candidates) > 1:
            names = ", ".join(category.name for category in candidates[:5])
            raise Conflict(
                str(CATEGORY_AMBIGUOUS) % {"said": said, "names": names},
                code="inventory.category_ambiguous",
            )
        category_id = candidates[0].pk if candidates else None
    found = categories.filter(pk=category_id)
    if hold:
        category = next(iter(held(found[:1])), None)
    else:
        category = (found.select_for_update() if lock else found).first()
    if category is None:
        raise NotFound(str(CATEGORY_NOT_FOUND))
    return category


def held(rows: QuerySet) -> list:
    """``rows``, each held until this transaction ends with a key-share lock taken in the same read, for a
    write that names them (a product put in a category, a tax category chosen): a deletion, the business's
    «Delete» or the Hub admin's, waits for this write, while another write that names them goes on, so two
    writes never wait for each other in a circle. One being deleted meanwhile is read once the deletion ends:
    gone, as one deleted before. The ORM has no ``FOR KEY SHARE``: it is appended to the SQL the ORM wrote,
    and the rows still come from the hub's database by the router."""
    try:
        sql, params = rows.query.sql_with_params()
    except EmptyResultSet:  # an empty ``__in``: nothing to read nor to hold
        return []
    return list(rows.model.objects.raw(f"{sql} FOR KEY SHARE", params))


def _first_match(queryset, lookups) -> list:
    """The rows of the first lookup that matches anything (in order of preference), at most six."""
    for lookup in lookups:
        rows = list(queryset.filter(lookup).order_by("name", "id")[:6])
        if rows:
            return rows
    return []


# Products


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
        "include_sold_out=true for every active product, sold out or not)."
    },
)
def list_products(ctx: OperationContext, params: ProductListIn) -> dict:
    products = filter_products(_products(current_settings()), params)
    return _page(products, params, _product_row)


@operation(
    "inventory.product.get",
    kind="query",
    permission="inventory.view_product",
    input=ProductRefIn,
    output=ProductOut,
    expose_api=True,
    ai={
        "description": "Get the full detail of one product, named by its id, its SKU or its name."
    },
)
def get_product(ctx: OperationContext, data: ProductRefIn) -> dict:
    return _product_row(
        find_product(data.id, data.product, rows=_products(current_settings()))
    )


@operation(
    "inventory.product.list_for_sale",
    kind="query",
    permission="inventory.view_product",
    input=ForSaleListIn,
    output=SaleProductPage,
    expose_api=True,
    ai={
        "description": "Sale catalog: the products on sale (active, not sold out) with what prices a sale line "
        "(price, cost, tax category, units) and whether a sale lowers their stock; never their stock."
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
    return _page(products.order_by("name", "id"), params, _sale_row)


@operation(
    "inventory.product.list_low_stock",
    kind="query",
    permission="inventory.view_product",
    input=LowStockListIn,
    output=LowStockPage,
    expose_api=True,
    ai={
        "description": "List the active articles with stock control at or under their low-stock threshold, the one with less first."
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
        "unit",
        "price_quantity",
        "pricing_unit",
    )
    return _page(
        products.order_by(params.sort, _tie_break(params.sort)),
        params,
        lambda product: {field: getattr(product, field) for field in fields},
    )


def filter_products(products, params: ProductFiltersIn):
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
    return products.order_by(params.sort, "id")


# Categories


@operation(
    "inventory.product_category.list",
    kind="query",
    permission="inventory.view_product",
    input=ProductCategoryListIn,
    output=ProductCategoryPage,
    expose_api=True,
    ai={
        "description": "Map each active product to its categories; the till filters its grid by category with it."
    },
)
def list_product_categories(
    ctx: OperationContext, params: ProductCategoryListIn
) -> dict:
    links = ProductCategory.objects.filter(
        product__is_deleted=False, product__is_active=True, category__is_deleted=False
    )
    if params.search:
        links = links.filter(
            Q(product__name__icontains=params.search)
            | Q(product__sku__icontains=params.search)
            | Q(category__name__icontains=params.search)
        )
    if params.product_id:
        links = links.filter(product_id=params.product_id)
    if params.category_id:
        links = links.filter(category_id=params.category_id)
    return _page(
        links.order_by("product_id", "category_id"),
        params,
        lambda link: {"product_id": link.product_id, "category_id": link.category_id},
    )


@operation(
    "inventory.category.list",
    kind="query",
    permission="inventory.view_category",
    input=CategoryListIn,
    output=CategoryPage,
    expose_api=True,
    ai={
        "description": "List the product categories, with how many active products each one has (sold out included)."
    },
)
def list_categories(ctx: OperationContext, params: CategoryListIn) -> dict:
    categories = _categories()
    if params.ids is not None:
        categories = categories.filter(id__in=params.ids)
    return _page(_filter_categories(categories, params), params, _category_row)


def _filter_categories(categories, params: CategoryFiltersIn):
    if params.search:
        categories = categories.filter(
            Q(name__icontains=params.search) | Q(slug__icontains=params.search)
        )
    categories = categories.filter(
        **_bounds(
            name__icontains=params.name,
            slug__icontains=params.slug,
            icon=params.icon,
            color=params.color,
            product_count__gte=params.product_count_min,
            product_count__lte=params.product_count_max,
        )
    )
    return categories.order_by(params.sort, _tie_break(params.sort))


# The ledger


@operation(
    "inventory.movement.list",
    kind="query",
    permission="inventory.view_stock",
    input=MovementListIn,
    output=MovementPage,
    expose_api=True,
    ai={
        "description": "The stock ledger, never edited: receptions, sales, voids, counts and write-offs, with "
        "the quantity, the balance left, the reason, the reference (sale or delivery note) and who made it."
    },
)
def list_movements(ctx: OperationContext, params: MovementListIn) -> dict:
    movements = StockMovement.objects.select_related("product").annotate(reference_label=_REFERENCE_LABEL)
    if params.search:
        movements = movements.filter(
            Q(product__name__icontains=params.search)
            | Q(product__sku__icontains=params.search)
            | _reference_matches(params.search)
        )
    if params.reference:
        movements = movements.filter(_reference_matches(params.reference))
    movements = movements.filter(
        **_bounds(
            movement_type=params.movement_type,
            product_id=params.product_id,
            created_at__gte=params.created_from,
            created_at__lte=params.created_to,
        )
    )
    return _page(
        movements.order_by(params.sort, _tie_break(params.sort)), params, _movement_row
    )


# The panel


@operation(
    "inventory.stock.get_summary",
    kind="query",
    permission="inventory.view_product",
    input=SummaryIn,
    output=SummaryOut,
    expose_api=True,
    ai={
        "description": "The inventory's figures: articles with stock control, in stock, out of stock, low on "
        "stock, without cost, the stock's value at cost and the number of active products."
    },
)
def get_summary(ctx: OperationContext, data: SummaryIn) -> dict:
    """The panel's figures over the active articles with stock control; a negative balance never subtracts."""
    tracked = Q(tracks=True)
    in_stock = tracked & Q(stock__gt=0)
    value = ExpressionWrapper(
        F("cost") * F("stock"),
        output_field=DecimalField(max_digits=32, decimal_places=3),
    )
    figures = (
        Product.objects.filter(is_deleted=False, is_active=True)
        .annotate(tracks=tracks_stock_expression(current_settings()))
        .aggregate(
            active_products=Count("id"),
            products_tracked=Count("id", filter=tracked),
            products_in_stock=Count("id", filter=in_stock),
            products_out_of_stock=Count("id", filter=tracked & Q(stock__lte=0)),
            products_low_stock=Count(
                "id", filter=tracked & Q(stock__lte=F("low_stock_threshold"))
            ),
            products_without_cost=Count("id", filter=tracked & Q(cost__lte=0)),
            value=Sum(value, filter=in_stock),
        )
    )
    total = figures.pop("value") or Decimal("0")
    return {
        **figures,
        "stock_value": int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    }


# Units and settings


@operation(
    "inventory.unit.list",
    kind="query",
    permission="inventory.view_product",
    input=UnitListIn,
    output=UnitPage,
    expose_api=True,
    ai={
        "description": "List the units of measure (code, kind, exact conversion factor and the step every quantity must fit)."
    },
)
def list_units(ctx: OperationContext, params: UnitListIn) -> dict:
    units = [
        {
            "code": code,
            "name": str(Unit(code).label),
            "category": spec.category,
            "factor_num": spec.factor.numerator,
            "factor_den": spec.factor.denominator,
            "increment": spec.increment,
            "is_reference": spec.is_reference,
        }
        for code, spec in ((code, UNIT_SPECS[code]) for code in Unit.values)
    ]
    if params.search:
        said = params.search.casefold()
        units = [
            unit
            for unit in units
            if said in unit["code"].casefold() or said in unit["name"].casefold()
        ]
    return {
        "rows": units[params.offset : params.offset + params.limit],
        "total": len(units),
        "limit": params.limit,
        "offset": params.offset,
    }


@operation(
    "inventory.config.get",
    kind="query",
    permission="inventory.manage_settings",
    input=ConfigGetIn,
    output=ConfigOut,
    expose_api=True,
    ai={
        "description": "Get the inventory settings: selling without stock, the default low-stock threshold and stock tracking."
    },
)
def get_config(ctx: OperationContext, data: ConfigGetIn) -> dict:
    return config_row(current_settings())


def config_row(settings: Settings) -> dict:
    return {
        "allow_sell_without_stock": settings.allow_sell_without_stock,
        "low_stock_threshold": settings.low_stock_threshold,
        "track_stock": settings.track_stock,
    }


# Exports: every row that matches, not a page, with the figures as the screen reads them


@operation(
    "inventory.product.export",
    kind="query",
    permission="inventory.export_product",
    input=ProductFiltersIn,
    output=ExportOut,
    expose_api=True,
    ai={
        "description": "Export to CSV every product that matches the search and the filters, with the headers the import reads."
    },
)
def export_products(ctx: OperationContext, params: ProductFiltersIn) -> dict:
    products = filter_products(_products(current_settings()), params)
    rows = [
        [
            _text_cell(product.name),
            _text_cell(product.sku),
            _money(product.price),
            _money(product.cost),
            quantity_text(product.stock),
            quantity_text(product.low_stock_threshold),
            _text_cell(product.ean13 or ""),
            _text_cell(product.description),
            product.unit,
            _text_cell(product.tax_category.key if product.tax_category else ""),
            str(YES if product.is_active else NO),
        ]
        for product in products
    ]
    return _csv(PRODUCTS_FILENAME, PRODUCT_HEADERS, rows)


@operation(
    "inventory.category.export",
    kind="query",
    permission="inventory.export_product",
    input=CategoryFiltersIn,
    output=ExportOut,
    expose_api=True,
    ai={
        "description": "Export the product categories to CSV: name, slug and number of active products."
    },
)
def export_categories(ctx: OperationContext, params: CategoryFiltersIn) -> dict:
    categories = _filter_categories(_categories(), params)
    rows = [
        [_text_cell(category.name), _text_cell(category.slug), str(category.product_count)]
        for category in categories
    ]
    return _csv(CATEGORIES_FILENAME, CATEGORY_HEADERS, rows)


def quantity_text(value: Decimal) -> str:
    """A quantity as the person reads it: exact, ungrouped, without trailing zeros (2,5 · 3 · 0,532)."""
    return format_decimal(
        value, locale=_locale(), group_separator=False, decimal_quantization=False
    )


# Helpers


def _bounds(**lookups) -> dict:
    """The lookups whose value was given (a filter left empty narrows nothing)."""
    return {lookup: value for lookup, value in lookups.items() if value is not None}


def _tie_break(sort: str) -> str:
    return "-id" if sort.startswith("-") else "id"


def _page(queryset, params, row) -> dict:
    return {
        "rows": [
            row(item) for item in queryset[params.offset : params.offset + params.limit]
        ],
        "total": queryset.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


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


def _product_row(product: Product) -> dict:
    fields = (
        "id",
        "name",
        "sku",
        "ean13",
        "description",
        "product_type",
        "price",
        "cost",
        "stock",
        "low_stock_threshold",
        "unit",
        "price_quantity",
        "pricing_unit",
        "tax_category_id",
        "track_stock",
        "is_active",
        "is_sold_out",
        "created_at",
        "updated_at",
    )
    return {
        **{field: getattr(product, field) for field in fields},
        "tax_category_key": product.tax_category.key if product.tax_category else None,
        "needs_tax_setup": needs_tax_setup(product),
        "tracks_stock": product.tracks,
        "category_ids": [link.category_id for link in product.live_links],
    }


def _sale_row(product: Product) -> dict:
    fields = (
        "id",
        "name",
        "sku",
        "product_type",
        "price",
        "cost",
        "tax_category_id",
        "unit",
        "price_quantity",
        "pricing_unit",
    )
    return {
        **{field: getattr(product, field) for field in fields},
        "tax_category_key": product.tax_category.key if product.tax_category else None,
        "needs_tax_setup": needs_tax_setup(product),
        "tracks_stock": product.tracks,
    }


def _categories():
    # What the till's strip counts is what its grid shows: the active articles, the sold-out ones greyed
    # among them (SALE-F07).
    active = Q(
        product_links__product__is_active=True,
        product_links__product__is_deleted=False,
    )
    return (
        Category.objects.filter(is_deleted=False)
        .select_related("tax_category")
        .annotate(product_count=Count("product_links", filter=active))
    )


def _category_row(category: Category) -> dict:
    fields = (
        "id",
        "name",
        "slug",
        "description",
        "icon",
        "color",
        "order",
        "tax_category_id",
        "product_count",
    )
    return {
        **{field: getattr(category, field) for field in fields},
        "tax_category_key": category.tax_category.key
        if category.tax_category
        else None,
    }


#: The movements whose reference is a sale of Sales (its id).
SALE_MOVEMENTS = (StockMovement.Type.SALE, StockMovement.Type.VOID, StockMovement.Type.REFUND)


def _sale_note_of(reference) -> QuerySet:
    """Inventory's note of the sale whose id is ``reference`` (the id as text: a delivery note is no uuid)."""
    return SaleStock.objects.annotate(key=Cast("sale_id", CharField())).filter(key=reference)


#: INVENTORY-F16: a sale reads as the number on its paper (its ticket or invoice, else the sale's own), noted
#: when its stock moved; another reference (a delivery note) reads as itself.
_REFERENCE_LABEL = Case(
    When(
        movement_type__in=SALE_MOVEMENTS,
        then=Coalesce(
            Subquery(
                _sale_note_of(OuterRef("reference"))
                .annotate(label=Coalesce(NullIf("document_number", Value("")), "sale_number"))
                .values("label")[:1]
            ),
            Value(""),
        ),
    ),
    default=F("reference"),
    output_field=CharField(),
)


def _reference_matches(text: str) -> Q:
    """The reference holds ``text``, or it is a sale whose ticket, invoice or own number does."""
    text = text.strip()
    numbered = SaleStock.objects.filter(Q(sale_number__icontains=text) | Q(document_number__icontains=text))
    return Q(reference__icontains=text) | Q(
        movement_type__in=SALE_MOVEMENTS,
        reference__in=numbered.annotate(key=Cast("sale_id", CharField())).values("key"),
    )


def _movement_row(movement: StockMovement) -> dict:
    fields = (
        "id",
        "product_id",
        "movement_type",
        "qty",
        "stock_after",
        "reason",
        "reference",
        "unit_cost",
        "actor",
        "created_at",
    )
    return {
        **{field: getattr(movement, field) for field in fields},
        "reference_label": movement.reference_label,
        "product_name": movement.product.name,
        "sku": movement.product.sku,
    }


def _locale() -> Locale:
    """The request's language as a CLDR locale (``es``, ``en``…), for babel."""
    return Locale.parse(translation.get_language() or settings.LANGUAGE_CODE, sep="-")


def _money(cents: int) -> str:
    """«2,20 €» in Spanish, «€2.20» in English (CLDR), ungrouped so that the import reads it back."""
    return format_currency(
        Decimal(cents) / 100, CURRENCY, locale=_locale(), group_separator=False
    )


def _text_cell(text: str) -> str:
    """A text cell of an export, with an apostrophe in front of what a spreadsheet would run.

    Only text: a figure (a stock of -3) is written as it is.
    """
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


def _csv(filename, headers, rows) -> dict:
    """A CSV with the delimiter Excel expects in the language: «;» where the comma is the decimal separator."""
    buffer = io.StringIO()
    writer = csv.writer(
        buffer, delimiter=";" if get_decimal_symbol(_locale()) == "," else ","
    )
    writer.writerow([str(header) for header in headers])
    writer.writerows(rows)
    return {
        "filename": str(filename),
        "content_type": CSV_CONTENT_TYPE,
        "content": BOM + buffer.getvalue(),
    }
