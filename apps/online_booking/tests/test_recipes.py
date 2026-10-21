"""The factory automation online booking brings to Automatizaciones (its ``recipes.py``; WORKBOOK
FLOW-F33): «Check each booking made online». Turned on from the gallery, a booking made on the public page
leaves the team a task naming the appointment, through the worker's real outbox relay, once.
"""

import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.context import OperationContext
from live.meta import all_live_app_configs

from apps.flow import recipes
from apps.online_booking import recipes as declared
from apps.task.models import Task
from base import catalog, worker
from base.catalog import RegisterResult

from .conftest import A, booking_data, public, run

pytestmark = pytest.mark.django_db

REF = "online_booking/booked_online"
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def owner() -> OperationContext:
    permissions = frozenset(p for config in all_live_app_configs() for p in config.permissions)
    return OperationContext(scope=A, actor="tester", permissions=permissions, language="en")


@pytest.fixture
def tick(monkeypatch):
    """One tick of the worker's real loop, without the SaaS and without releasing the test's connection."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def once() -> None:
        stop = threading.Event()
        now = timezone.now()
        assert worker.run(stop, tick_seconds=0, wait=lambda _seconds: stop.set() or True, clock=lambda: now) == 0

    return once


def test_online_booking_declares_check_each_booking_and_automations_offers_it():
    assert [recipe["id"] for recipe in declared.RECIPES] == ["booked_online"]
    recipe = recipes.find(REF)
    assert recipes.grants(recipe) == ["task.task.create"]
    assert recipes.words(recipe, "es")["name"] == "Revisar cada cita reservada por internet"
    assert recipes.build(recipe, "es")["steps"][0]["params"]["title"] == "Revisar la reserva por internet {{input.number}}"


def test_turned_on_a_booking_made_online_leaves_a_task_naming_it_once(salon, tick):
    run("flow.recipe.enable", {"recipe": REF}, ctx=owner())

    booked = public("book", booking_data(salon, "10:00"))
    tick()

    assert list(Task.objects.values_list("title", "priority")) == [(f"Check the online booking {booked.number}", "medium")]
    tick()
    assert Task.objects.count() == 1
