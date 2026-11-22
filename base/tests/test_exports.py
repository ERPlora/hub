"""``base.exports.visible_columns``: the columns of an export, read from the schema of its rows, without the ones marked
with a data permission the caller lacks, so a CSV never carries what its screen would show empty (BASE-F119)."""

from live.context import OperationContext
from pydantic import BaseModel, Field

from base.exports import visible_columns
from base.sensitive import COSTS, VIEW_COSTS
from base.tenancy.tests.business import A


class LineRow(BaseModel):
    name: str
    cost: str = Field(json_schema_extra=COSTS)
    stock: str


def caller(*permissions: str) -> OperationContext:
    return OperationContext(scope=A, actor="tester", permissions=frozenset(permissions))


def test_a_column_marked_with_a_permission_the_caller_lacks_is_left_out_and_the_rest_keep_their_order():
    assert visible_columns(caller(), LineRow) == ["name", "stock"]


def test_with_the_permission_every_column_in_its_order():
    assert visible_columns(caller(VIEW_COSTS), LineRow) == ["name", "cost", "stock"]
