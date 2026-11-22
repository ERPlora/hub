"""Whether a Home panel opens to a person: its own permission, and every data permission its figure needs.

A panel's figure is a field of its operation's answer (the values of its ``map``). When that field is marked with a
data permission (``base.sensitive``), whoever lacks it would get the panel empty, so the panel is not theirs at all.
"""

import pytest
from live.context import OperationContext
from live.meta import Widget
from live.operations import Operation, registry
from pydantic import BaseModel, Field

from base import visibility
from base.sensitive import COSTS, VIEW_COSTS
from base.tenancy.tests.business import A


class FiguresIn(BaseModel):
    pass


class FiguresOut(BaseModel):
    stock_value: float | None = Field(None, json_schema_extra=COSTS)
    products_in_stock: int = 0


class RowOut(BaseModel):
    name: str = ""
    unit_cost: float | None = Field(None, json_schema_extra=COSTS)


class RowsOut(BaseModel):
    rows: list[RowOut] = []


@pytest.fixture(autouse=True)
def figures(monkeypatch):
    for name, output in (("stock.figures.get", FiguresOut), ("stock.rows.list", RowsOut)):
        monkeypatch.setitem(
            registry,
            name,
            Operation(
                name=name,
                kind="query",
                permission=None,
                input=FiguresIn,
                output=output,
                expose_api=False,
                ai=None,
                fn=lambda ctx, data: {},
            ),
        )


def ctx(*permissions):
    return OperationContext(scope=A, actor="ana", permissions=frozenset(permissions), language="en")


def panel(**fields):
    return Widget(key="panel", title="Panel", kind="kpi", **fields)


def test_a_panel_whose_figure_is_a_cost_is_only_for_who_sees_costs():
    value = panel(operation="stock.figures.get", map={"value": "stock_value"})
    assert visibility.widget_open(ctx(), value) is False
    assert visibility.widget_open(ctx(VIEW_COSTS), value) is True


def test_a_cost_inside_the_rows_of_its_answer_closes_it_too():
    rows = panel(operation="stock.rows.list", map={"label": "name", "value": "unit_cost"})
    assert visibility.widget_open(ctx(), rows) is False
    assert visibility.widget_open(ctx(VIEW_COSTS), rows) is True


def test_a_panel_reading_an_unmarked_field_of_the_same_answer_is_for_everybody():
    count = panel(operation="stock.figures.get", map={"value": "products_in_stock"})
    assert visibility.widget_open(ctx(), count) is True


def test_its_own_permission_still_closes_it():
    value = panel(operation="stock.figures.get", map={"value": "stock_value"}, permission="stock.view")
    assert visibility.widget_open(ctx(VIEW_COSTS), value) is False
    assert visibility.widget_open(ctx(VIEW_COSTS, "stock.view"), value) is True


def test_a_panel_drawn_by_a_component_or_an_unknown_operation_goes_by_its_permission():
    assert visibility.widget_open(ctx(), Widget(key="chart", title="Chart", component="StockChart")) is True
    assert visibility.widget_open(ctx(), panel(operation="stock.unknown", map={"value": "stock_value"})) is True
    assert visibility.widget_open(ctx(), panel(operation="stock.unknown", permission="stock.view")) is False
