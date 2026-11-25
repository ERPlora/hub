"""The bell by the clock: how often the bell reads a module's counters again (``bell_refresh_every``)."""

from types import SimpleNamespace

import pytest
from live.meta import BellCounter

from base import home


UNSET = object()


def bell_module(refresh=UNSET, label="printing", keys=("stalled",)):
    """A module with the counters ``keys`` in its bell and, unless ``UNSET``, ``bell_refresh_every = refresh``."""
    module = SimpleNamespace(
        label=label, bell=[BellCounter(key=key, operation=f"{label}.thing.count", route="/", label="L") for key in keys]
    )
    if refresh is not UNSET:
        module.bell_refresh_every = refresh
    return module


@pytest.mark.parametrize(
    ("refresh", "errors"),
    [
        (UNSET, 0),
        ({}, 0),
        ({"stalled": home.bell_counters.MIN_BELL_REFRESH_SECONDS}, 0),
        ({"stalled": 60}, 0),
        (60, 1),  # not per counter
        ({"other": 60}, 1),  # no such counter in its bell
        ({"stalled": home.bell_counters.MIN_BELL_REFRESH_SECONDS - 1}, 1),  # every open screen a poller
        ({"stalled": True}, 1),
        ({"stalled": 60.0}, 1),
        ({"stalled": "60"}, 1),
    ],
)
def test_how_often_a_counter_is_read_again_is_checked_at_start(refresh, errors):
    found = home.bell_counters.bell_refresh_errors([bell_module(refresh)])
    assert len(found) == errors
    assert all(error.id == "base.E007" for error in found)


def test_the_check_of_the_bells_clock_runs_with_the_others(monkeypatch):
    from django.core import checks

    monkeypatch.setattr("base.home.bell_counters.all_live_app_configs", lambda: [bell_module({"other": 60})])
    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E007"] == ["base.E007"]
