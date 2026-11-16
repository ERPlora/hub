"""The factory automation online booking brings to Automatizaciones (its ``recipes.py``; WORKBOOK
FLOW-F33): «Check each booking made online». Turned on from the gallery, a booking made on the public page
leaves the team a task naming the appointment, through the worker's real outbox relay, once.
"""

from live.context import OperationContext
from live.meta import all_live_app_configs

from apps.flow import recipes
from apps.online_booking import recipes as declared
from apps.task.models import Task

from .conftest import HUB_DB, HUB_DB_COMMITTED, A, booking_data, public, run

REF = "online_booking/booked_online"


def owner() -> OperationContext:
    permissions = frozenset(p for config in all_live_app_configs() for p in config.permissions)
    return OperationContext(scope=A, actor="tester", permissions=permissions, language="en")


@HUB_DB
def test_online_booking_declares_check_each_booking_and_automations_offers_it():
    assert [recipe["id"] for recipe in declared.RECIPES] == ["booked_online"]
    recipe = recipes.find(A, REF)
    assert recipes.grants(recipe) == ["task.task.create"]
    assert recipes.words(recipe, "es")["name"] == "Revisar cada cita reservada por internet"
    assert recipes.build(recipe, "es")["steps"][0]["params"]["title"] == "Revisar la reserva por internet {{input.number}}"


@HUB_DB_COMMITTED
def test_turned_on_a_booking_made_online_leaves_a_task_naming_it_once(salon, worker_loop):
    run("flow.recipe.enable", {"recipe": REF}, ctx=owner())

    booked = public("book", booking_data(salon, "10:00"))
    worker_loop()

    assert list(Task.objects.values_list("title", "priority")) == [(f"Check the online booking {booked.number}", "medium")]
    worker_loop()
    assert Task.objects.count() == 1
