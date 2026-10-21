"""The factory automation Citas brings to Automatizaciones (its ``recipes.py``; WORKBOOK FLOW-F33):
«Fill the gap when a customer cancels». Turned on from the gallery, a cancellation the customer asks for
leaves the team a task, through the worker's real outbox relay; one the team makes leaves nothing.
"""

import datetime as dt
import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.context import OperationContext
from live.meta import all_live_app_configs
from live.operations import get

from apps.appointment import recipes as declared
from apps.flow import recipes
from apps.task.models import Task
from base import catalog, worker
from base.catalog import RegisterResult

from .conftest import A, TESTER, make_appointment, make_customer, make_member, make_service, make_settings

pytestmark = pytest.mark.django_db

REF = "appointment/customer_cancelled"
REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def owner(language: str = "en") -> OperationContext:
    permissions = frozenset(p for config in all_live_app_configs() for p in config.permissions)
    return OperationContext(scope=A, actor=TESTER, permissions=permissions, language=language)


def run(name: str, data: dict, ctx: OperationContext | None = None):
    op = get(name)
    return op(ctx or owner(), op.input.model_validate(data))


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


def test_citas_declares_fill_the_gap_and_automations_offers_it():
    assert [recipe["id"] for recipe in declared.RECIPES] == ["customer_cancelled"]
    recipe = recipes.find(REF)
    assert recipes.grants(recipe) == ["task.task.create"]
    assert recipes.words(recipe, "es") == {
        "name": "Cubrir el hueco cuando un cliente cancela",
        "summary": "Cuando un cliente cancela su cita, te deja una tarea para cubrir el hueco.",
        "description": "Solo con las cancelaciones que pide el cliente: las que hace tu equipo no la arrancan. "
        "La tarea es de prioridad alta y dice qué cita era.",
    }


def test_turned_on_a_cancellation_the_customer_asks_for_leaves_a_task_and_one_by_the_team_does_not(tick):
    make_settings(allow_customer_cancellation=True, cancellation_notice_hours=0)
    lucia = make_customer("Lucía Pérez")
    ana = make_member("Ana", "López")
    haircut = make_service("Haircut", price=2000, duration=30)
    start = timezone.now() + dt.timedelta(days=3)
    hers = make_appointment(lucia, ana, [haircut], start, number="APT-TEST-0101")
    ours = make_appointment(lucia, ana, [haircut], start + dt.timedelta(hours=2), number="APT-TEST-0102")
    run("flow.recipe.enable", {"recipe": REF})

    run("appointment.appointment.cancel", {"id": str(hers.id), "on_behalf_of_customer": True, "customer": "Lucía Pérez"})
    run("appointment.appointment.cancel", {"id": str(ours.id)})
    tick()

    assert list(Task.objects.values_list("title", "priority")) == [("Fill the gap of appointment APT-TEST-0101", "high")]
    tick()
    assert Task.objects.count() == 1
