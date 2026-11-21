"""The units of measure (``inventory.unit.list``)."""

from live.context import OperationContext
from live.operations import operation

from apps.inventory.models import UNIT_SPECS, Unit
from apps.inventory.schemas import UnitListIn, UnitPage


@operation(
    "inventory.unit.list",
    kind="query",
    permission="inventory.view_product",
    input=UnitListIn,
    output=UnitPage,
    expose_api=True,
    ai={
        "description": "List the units of measure (code, kind, exact conversion factor and the step every quantity must fit).",
        "asks": {
            "en": (
                "what units of measure are set up in this business?",
                "which units can I sell in, kilos, litres?",
            ),
            "es": (
                "¿qué unidades de medida tengo configuradas en este negocio?",
                "¿qué unidades de medida hay, kilos, litros, piezas?",
            ),
        },
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
