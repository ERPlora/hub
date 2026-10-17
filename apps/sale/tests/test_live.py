"""Live queries of the sale app: which events re-run which screen."""

from pathlib import Path

from live.live_registry import live_registry

from apps.sale import events

EVENTS_SOURCE = Path(events.__file__).read_text()


def sale_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("sale.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_live_queries():
    assert set(sale_queries()) == {
        "sale.sale.list",
        "sale.sale.get",
        "sale.sale.stats",
        "sale.sale.today",
        "sale.sale.last_7_days",
        "sale.sale.by_staff",
        "sale.order.list",
        "sale.order.get",
        "sale.checkout.preview",
        "sale.payment_method.list",
        "sale.settings.get",
        "sale.pos_settings.get",
        "sale.department.list",
        "sale.quick_note.list",
        "sale.refund.options",
        "sale.refund.list",
    }


def test_every_event_is_a_literal_of_an_events_module():
    tax_events = Path(__file__).parents[2].joinpath("tax", "events.py").read_text()
    for on in sale_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE or f'"{event}"' in tax_events, event


def test_a_charge_re_runs_the_sales_the_figures_and_the_checks():
    affected = live_registry.affected([events.SALE_COMPLETED])
    assert affected >= {
        "sale.sale.list",
        "sale.sale.stats",
        "sale.sale.today",
        "sale.order.list",
        "sale.order.get",
        "sale.checkout.preview",
    }
    assert "sale.quick_note.list" not in affected


def test_a_change_of_the_check_re_runs_the_check_and_its_preview_but_not_the_sales():
    affected = live_registry.affected([events.ORDER_CHANGED])
    assert affected >= {"sale.order.get", "sale.order.list", "sale.checkout.preview"}
    assert "sale.sale.list" not in affected


def test_a_new_tax_rule_re_runs_the_preview_and_the_departments():
    affected = live_registry.affected(["tax.rule.created"])
    assert {"sale.checkout.preview", "sale.department.list"} <= affected


def test_the_settings_re_run_the_methods_allowed_and_the_preview():
    affected = live_registry.affected([events.SETTINGS_UPDATED])
    assert {
        "sale.settings.get",
        "sale.pos_settings.get",
        "sale.payment_method.list",
        "sale.checkout.preview",
    } <= affected

