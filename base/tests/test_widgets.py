"""The panels a person may put on their dashboard, as the modules declare them (``widgets``)."""

from types import SimpleNamespace

from django.utils.translation import gettext_lazy, override
from live.context import OperationContext, Scope
from live.meta import Widget

from base import home


def person(*permissions):
    return OperationContext(scope=Scope("host", "a"), actor="ana", permissions=frozenset(permissions), language="en")


def module(*panels):
    return SimpleNamespace(label="things", verbose_name="Things", widgets=list(panels))


def test_lazy_translations_become_text_at_any_depth_and_nothing_else_changes():
    failed = gettext_lazy("Failed events")

    with override("es"):
        found = home.widgets.translated({"label": failed, "rows": [(1, failed)], "count": 3})

    assert found == {"label": "Eventos caídos", "rows": [[1, "Eventos caídos"]], "count": 3}


def test_a_panel_says_its_module_and_its_props_in_the_active_language():
    panel = Widget(key="today", title=gettext_lazy("Failed events"), component="ThingsToday", options={"hint": gettext_lazy("Failed events")})

    with override("es"):
        (found,) = home.widgets.widgets(person(), [module(panel)], "restaurant")

    assert found == {
        "key": "things.today",
        "app": "things",
        "title": "Eventos caídos",
        "icon": "",
        "category": "Things",
        "size": "md",
        "default": False,
        "kind": None,
        "operation": None,
        "params": {},
        "map": {},
        "options": {"hint": "Eventos caídos"},
        "component": "ThingsToday",
        "refresh_on": [],
        "live": False,
    }


def test_a_panel_is_left_out_without_its_permission_or_outside_its_verticals():
    guarded = Widget(key="money", title="Money", permission="things.view", component="Money")
    salon = Widget(key="chairs", title="Chairs", verticals=("salon",), component="Chairs")
    configs = [module(guarded, salon)]

    assert home.widgets.widgets(person(), configs, "restaurant") == []
    assert [panel["key"] for panel in home.widgets.widgets(person("things.view"), configs, "salon")] == [
        "things.money",
        "things.chairs",
    ]
