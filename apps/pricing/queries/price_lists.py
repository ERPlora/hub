"""Read operations of the price lists."""

from django.db.models import Q
from django.db.models.functions import Lower
from live.context import OperationContext
from live.operations import operation

from apps.pricing.queries.reads import _page, find_list
from apps.pricing.queries.rows import _lists, _status, list_row
from apps.pricing.schemas.fields import Page
from apps.pricing.schemas.price_lists import PriceListListIn, PriceListOut, PriceListRefIn
from base.ordering import list_order


@operation(
    "pricing.price_list.list",
    kind="query",
    permission="pricing.view",
    input=PriceListListIn,
    output=Page[PriceListOut],
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who do I give special conditions to?",
                "show me the special conditions for partners and distributors",
                "how many special conditions are still in force?",
            ),
            "es": (
                "¿para quién tengo condiciones especiales?",
                "enséñame las condiciones de socios y distribuidores",
                "¿cuántas condiciones especiales siguen en vigor?",
            ),
        },
        "description": "List the price lists (the active ones by default): code, name, currency, whether the "
        "prices carry the tax, customer group, dates, whether it is the general list and how many prices it has. "
        "Search by code or name; filter by currency, group, tax or status."
    },
)
def list_price_lists(ctx: OperationContext, params: PriceListListIn) -> dict:
    rows = _status(_lists(), params.status)
    if params.search:
        rows = rows.filter(Q(code__icontains=params.search) | Q(name__icontains=params.search))
    for column in ("code", "name", "currency"):
        value = getattr(params, column)
        if value:
            rows = rows.filter(**{f"{column}__icontains": value})
    if params.customer_group_id:
        rows = rows.filter(customer_group_id=params.customer_group_id)
    if params.tax_basis == "business":
        rows = rows.filter(tax_included__isnull=True)
    elif params.tax_basis:
        rows = rows.filter(tax_included=params.tax_basis == "included")
    rows = rows.order_by(*list_order(params.sort, Lower("code"), descending=params.dir == "desc", nulls_last=True))
    return _page(rows, params, list_row)


@operation(
    "pricing.price_list.get",
    kind="query",
    permission="pricing.view",
    input=PriceListRefIn,
    output=PriceListOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "is the Hospitality one valid all year or does it end?",
                "give me the details of Hospitality, HOST-24",
                "until when is Hospitality valid?",
            ),
            "es": (
                "¿lo de Hostelería vale todo el año o caduca?",
                "dame el detalle de Hostelería, la HOST-24",
                "¿qué fechas tiene la de Hostelería?",
            ),
        },
        "description": "Get one price list by its id, its code or its name (e.g. «wholesale list»).",
    },
)
def get_price_list(ctx: OperationContext, data: PriceListRefIn) -> dict:
    return list_row(find_list(data.id, data.price_list, rows=_lists()))
