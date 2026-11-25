"""Whether the floor plan is set up (``table.floor.status``): how many tables are in use and how many zones there are."""

from live.context import OperationContext
from live.operations import operation

from apps.table.models import Table, Zone
from apps.table.schemas import FloorStatusOut, NoIn


@operation(
    "table.floor.status",
    kind="query",
    permission="table.view_table",
    input=NoIn,
    output=FloorStatusOut,
    ai={
        "description": "Whether the floor plan is set up: how many tables are in use and how many zones there are.",
        "asks": {
            "en": (
                "is my floor plan set up?",
                "how many tables do I have in use?",
            ),
            "es": (
                "¿tengo montado el plano de la sala?",
                "¿cuántas mesas tengo en uso?",
            ),
        },
    },
)
def floor_status(ctx: OperationContext, params: NoIn) -> dict:
    return {
        "usable_tables": Table.objects.filter(is_deleted=False, is_active=True).count(),
        "zones": Zone.objects.filter(is_deleted=False).count(),
    }
