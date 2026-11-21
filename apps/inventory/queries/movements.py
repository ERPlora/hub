"""The stock ledger (``inventory.movement.list``), never edited, with the reference a sale's movement reads
as: the number on its paper."""

from django.db.models import Case, CharField, F, OuterRef, Q, QuerySet, Subquery, Value, When
from django.db.models.functions import Cast, Coalesce, NullIf
from live.context import OperationContext
from live.operations import operation

from apps.inventory.models import SaleStock, StockMovement
from apps.inventory.queries.reads import _bounds, _page
from apps.inventory.schemas import MovementListIn, MovementPage
from base.ordering import list_order_for


@operation(
    "inventory.movement.list",
    kind="query",
    permission="inventory.view_stock",
    input=MovementListIn,
    output=MovementPage,
    expose_api=True,
    ai={
        "description": "The stock ledger, never edited: receptions, sales, voids, counts and write-offs, with "
        "the quantity, the balance left, the reason, the reference (sale or delivery note) and who made it.",
        "asks": {
            "en": (
                "show me the history of stock coming in and going out",
                "what stock movements were there this week?",
                "who changed the stock of the coffee?",
            ),
            "es": (
                "¿qué entradas, salidas y ajustes de stock ha habido esta semana?",
                "enséñame el historial de movimientos del café",
                "¿quién tocó el stock del té?",
            ),
        },
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
        movements.order_by(*list_order_for(params.sort)), params, _movement_row
    )


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
