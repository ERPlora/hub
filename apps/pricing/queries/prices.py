"""Read operations of the prices of a price list."""

from django.db.models import CharField, Q
from django.db.models.functions import Coalesce, Lower
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.pricing.queries.reads import ITEM_NOT_FOUND, _page, find_list, live_items
from apps.pricing.queries.rows import item_label, item_row
from apps.pricing.schemas.fields import Page
from apps.pricing.schemas.prices import PriceItemDetailOut, PriceItemIdIn, PriceItemListIn, PriceItemOut
from base.ordering import list_order


@operation(
    "pricing.price_item.list",
    kind="query",
    permission="pricing.view",
    input=PriceItemListIn,
    output=Page[PriceItemOut],
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how much is the croissant in each one?",
                "what does the croissant go for everywhere?",
                "show me one by one what each thing costs in Hospitality",
            ),
            "es": (
                "¿cuánto cuesta el croissant en cada una?",
                "¿a cuánto va el croissant en todas?",
                "enséñame uno por uno lo que cuesta cada cosa en la de Hostelería",
            ),
        },
        "description": "List the prices of a price list (named by its code or name), or the prices of one product "
        "or service across every list: the article, its catalog price, the from quantity and the price in cents. "
        "Search by product name or SKU or by service name."
    },
)
def list_price_items(ctx: OperationContext, params: PriceItemListIn) -> dict:
    rows = live_items().select_related("price_list", "product")
    if params.price_list_id or params.price_list:
        rows = rows.filter(price_list=find_list(params.price_list_id, params.price_list))
    if params.product_id:
        rows = rows.filter(product_id=params.product_id)
    if params.service_id:
        rows = rows.filter(service_id=params.service_id)
    if params.kind:
        rows = rows.filter(product__isnull=params.kind == "service")
    if params.search:
        rows = rows.filter(
            Q(product__name__icontains=params.search)
            | Q(product__sku__icontains=params.search)
            | Q(service_name__icontains=params.search)
        )
    rows = rows.annotate(shown_name=Lower(Coalesce("product__name", "service_name", output_field=CharField())))
    column = {"name": "shown_name"}.get(params.sort, params.sort)
    rows = rows.order_by(*list_order(column, "min_quantity", descending=params.dir == "desc", nulls_last=True))
    return _page(rows, params, item_row)


@operation(
    "pricing.price_item.get",
    kind="query",
    permission="pricing.view",
    input=PriceItemIdIn,
    output=PriceItemDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "from how many does the beer's amount in the partners' one apply?",
                "give me the details of the croissant in the partners' one",
                "what exactly does a beer go for with the partners?",
            ),
            "es": (
                "¿a partir de cuántas vale lo de la caña de los socios?",
                "dame el detalle de lo del croissant en la de socios",
                "¿a cuánto va exactamente la caña para los socios?",
            ),
        },
        "description": "Get one price of a price list by its id (see pricing.price_item.list): the article, its list "
        "and the list's currency, the from quantity and the price in cents of that currency."
    },
)
def get_price_item(ctx: OperationContext, data: PriceItemIdIn) -> dict:
    item = live_items().select_related("price_list", "product").filter(pk=data.id).first()
    if item is None:
        raise NotFound(str(ITEM_NOT_FOUND), code="pricing.price_item_not_found")
    row = item_row(item)
    return {**row, "label": item_label(row, ctx.language)}
