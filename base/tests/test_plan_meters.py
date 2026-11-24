"""What an app says its plan includes (BASE-F40: «Usage and plan» of System)."""

from types import SimpleNamespace

import pytest

from base import home


def metered(**declared):
    spec = {"operation": "demo.item.list", "used": "used", "limit": "limit", "label": "Things", **declared}
    return SimpleNamespace(label="things", plan_meter=spec)


def test_a_meter_says_what_its_app_answers(monkeypatch):
    monkeypatch.setattr(home.plan_meters, "run_hook", lambda ctx, operation, params: {"used": 40, "limit": 150})

    assert home.plan_meters.plan_meters(None, [metered()]) == [
        {"key": "things", "label": "Things", "used": 40, "limit": 150, "available": True}
    ]


def test_an_app_that_declares_no_meter_is_left_out(monkeypatch):
    monkeypatch.setattr(home.plan_meters, "run_hook", lambda ctx, operation, params: pytest.fail("nothing to ask"))

    assert home.plan_meters.plan_meters(None, [SimpleNamespace(label="things")]) == []


def test_a_meter_whose_figures_were_never_measured_says_so_never_a_zero(monkeypatch):
    monkeypatch.setattr(home.plan_meters, "run_hook", lambda ctx, operation, params: {"used": 0, "limit": 0, "since": None})

    assert home.plan_meters.plan_meters(None, [metered(measured="since")]) == [
        {"key": "things", "label": "Things", "used": None, "limit": None, "available": True}
    ]


def test_a_meter_measured_gives_its_figures_even_at_zero(monkeypatch):
    monkeypatch.setattr(home.plan_meters, "run_hook", lambda ctx, operation, params: {"used": 0, "limit": 0, "since": "2026-10-01"})

    assert home.plan_meters.plan_meters(None, [metered(measured="since")]) == [
        {"key": "things", "label": "Things", "used": 0, "limit": 0, "available": True}
    ]


def test_a_meter_that_fails_is_unavailable_and_the_others_go_on(monkeypatch, caplog):
    def fails_for_broken(ctx, operation, params):
        if operation == "broken":
            raise RuntimeError("its query failed")
        return {"used": 1, "limit": 2}

    monkeypatch.setattr(home.plan_meters, "run_hook", fails_for_broken)

    meters = home.plan_meters.plan_meters(None, [metered(operation="broken"), metered()])

    assert meters == [
        {"key": "things", "label": "Things", "used": None, "limit": None, "available": False},
        {"key": "things", "label": "Things", "used": 1, "limit": 2, "available": True},
    ]
    assert "left out" in caplog.text


def test_a_meter_says_its_label_in_the_active_language(monkeypatch):
    from django.utils.translation import gettext_lazy, override

    monkeypatch.setattr(home.plan_meters, "run_hook", lambda ctx, operation, params: {"used": 1, "limit": 2})

    with override("es"):
        assert home.plan_meters.plan_meters(None, [metered(label=gettext_lazy("Failed events"))])[0]["label"] == "Eventos caídos"


@pytest.mark.parametrize(
    ("declared", "errors"),
    [
        (None, 0),
        ({"operation": "base.plan.usage", "used": "known", "limit": "demo", "label": "X"}, 0),
        ({"operation": "base.plan.usage", "used": "known", "limit": "demo", "label": "X", "measured": "plan_slug"}, 0),
        ("base.plan.usage", 1),
        ({"operation": "nothing.at.all", "used": "known", "limit": "demo", "label": "X"}, 1),
        ({"operation": "base.plan.usage", "used": "nope", "limit": "demo", "label": "X"}, 1),
        ({"operation": "base.plan.usage", "used": "known", "limit": "nope", "label": "X"}, 1),
        ({"operation": "base.plan.usage", "used": "known", "limit": "demo", "label": "X", "measured": "nope"}, 1),
        ({"operation": "base.plan.usage", "used": "known", "limit": "demo"}, 1),
    ],
)
def test_what_an_app_declares_as_its_meter_is_checked_at_start(declared, errors):
    found = home.plan_meters.plan_meter_errors([SimpleNamespace(label="things", plan_meter=declared)])

    assert len(found) == errors
    assert all(error.id == "base.E013" for error in found)


def test_the_check_of_the_meters_runs_with_the_others(monkeypatch):
    from django.core import checks

    monkeypatch.setattr("base.home.plan_meters.all_live_app_configs", lambda: [SimpleNamespace(label="things", plan_meter="nope")])

    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E013"] == ["base.E013"]
