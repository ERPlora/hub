"""Printing in the Home's health row (BASE-F02): who runs the business is told whether the receipt station answers now,
with Printing's own reading (``printing.device.health``), the same one System's «Your printer» reads. Nothing while
Printing is off, and nothing for whoever does not run the business.

base and printing run for real: the row comes from PrintingConfig through ``base.health.list``, as the person.
"""

import dataclasses
import datetime as dt

import pytest
from live.operations import get

from apps.printing.tests.conftest import B, HUB_DB, ctx_for, printer, reaches, run
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas.health import HealthListIn
from base.tenancy.context import use_hub

pytestmark = HUB_DB


def row(ctx) -> dict | None:
    """Printing's item of the health row for the person of ``ctx`` (``None``: not told)."""
    items = get("base.health.list")(ctx, HealthListIn()).model_dump(mode="json")["items"]
    found = [item for item in items if item["app"] == "printing"]
    assert len(found) <= 1, found
    return found[0] if found else None


@pytest.mark.parametrize(
    ("seen", "state", "title", "action"),
    [
        (None, "not_configured", "Printer not set up", "Set up printing"),
        (dt.timedelta(seconds=95), "no_signal", "Printer not connected", "Set up printing"),
        (dt.timedelta(seconds=5), "ok", "Printer ready", None),
    ],
)
def test_who_runs_the_business_is_told_whether_the_receipt_station_answers(seen, state, title, action):
    if seen is not None:
        reaches(printer("Till"), seen=seen)

    assert row(ctx_for("hub_owner")) == {
        "key": "printing",
        "app": "printing",
        "state": state,
        "title": title,
        "action": action,
        "route": "/printing/printers" if action else None,
    }


def test_it_says_it_in_the_persons_language():
    reaches(printer("Till"), seen=dt.timedelta(seconds=95))

    item = row(ctx_for("hub_admin", language="es"))

    assert (item["title"], item["action"]) == ("Impresora sin conectar", "Configurar la impresión")


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_whoever_does_not_run_the_business_is_not_told(role):
    reaches(printer("Till"))

    assert row(ctx_for(role)) is None


def test_who_runs_the_business_without_a_permission_of_printing_is_not_told():
    reaches(printer("Till"))
    runs_it_only = dataclasses.replace(ctx_for("hub_employee"), permissions=frozenset({VIEW_HOME, ADMINISTER_HUB}))

    assert row(runs_it_only) is None


def test_with_printing_off_the_row_says_nothing_of_it_and_the_other_business_keeps_it(hub_b):
    run("base.app.disable", {"app": "printing"}, dataclasses.replace(ctx_for(), permissions=frozenset({"*"})))

    assert row(ctx_for("hub_owner")) is None
    with use_hub(hub_b):
        assert row(ctx_for("hub_owner", scope=B))["state"] == "not_configured"
