"""What a CSV export carries: the columns of its rows that the caller sees."""

from live.context import OperationContext
from live.sensitive import required_permission
from pydantic import BaseModel


def visible_columns(ctx: OperationContext, row: type[BaseModel]) -> list[str]:
    """The fields of ``row``, the schema of an export's rows, in their order, without those marked with a data
    permission ``ctx`` lacks (``live.sensitive``): a file never carries what its screen would give empty."""
    return [name for name, field in row.model_fields.items() if ctx.has(required_permission(field))]
