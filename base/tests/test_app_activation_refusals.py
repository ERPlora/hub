"""What an app refuses, said beforehand: the hooks ``can_enable`` and ``can_disable`` an app declares on its
config, the reason ``base.app.list`` gives for each app, and that turning one off and on again keeps its data.
"""

import pytest
from django.apps import apps
from live.errors import Conflict

from base import events
from base.activation import OFF, Activation
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.test_app_activation import app_list, by_id, ctx, disable, enable, recorded, rows, set_rows

#: Business A entered for every test with the database.
__all__ = ["in_business_a"]


# ── What an app refuses, said beforehand (hub#618, hub#619, hub#694) ─────────────────────────────────────────────


@HUB_DB
def test_an_app_may_refuse_to_go_on_with_its_reason(monkeypatch):
    seen = []

    def refuse(context):
        seen.append(context.scope)
        return f"Not for {context.scope.key}."

    monkeypatch.setattr(apps.get_app_config("task"), "can_enable", refuse, raising=False)
    set_rows(flow="on*")

    with pytest.raises(Conflict) as refused:
        enable("task")

    error = refused.value.envelope()["error"]
    assert (refused.value.status, error["code"], error["app"]) == (409, "base.app_vetoed", "task")
    assert refused.value.message == "Not for tenant-a."
    assert seen == [A]
    assert rows()["task"] == Activation(OFF, False)
    assert recorded(events.APP_ENABLED) == []


@HUB_DB
def test_what_would_come_along_may_refuse_too_and_nothing_goes_on(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("staff"), "can_enable", lambda ctx: "No staff here.", raising=False)
    set_rows(flow="on*")

    with pytest.raises(Conflict) as refused:
        enable("task")

    assert refused.value.envelope()["error"]["app"] == "staff"
    assert refused.value.message == "No staff here."
    assert (rows()["task"], rows()["staff"]) == (Activation(OFF, False), Activation(OFF, False))


@HUB_DB
def test_the_refusal_to_go_on_is_said_in_the_language_of_who_asks(monkeypatch):
    from django.utils.translation import gettext

    monkeypatch.setattr(
        apps.get_app_config("task"), "can_enable", lambda ctx: gettext("Turn off %(apps)s first.") % {"apps": "X"}, raising=False
    )
    set_rows(flow="on*")

    with pytest.raises(Conflict) as refused:
        enable("task", context=ctx(language="es"))

    assert refused.value.message == "Desactiva antes X."


@HUB_DB
def test_an_app_already_on_is_never_asked_to_go_on(monkeypatch):
    """Choosing what came along turns nothing on: an app that refuses to go on stays as it is, chosen by the person."""
    monkeypatch.setattr(apps.get_app_config("staff"), "can_enable", lambda ctx: "No staff here.", raising=False)
    set_rows(task="on*", staff="on")

    answer = enable("staff")

    assert (answer["state"], answer["chosen"]) == ("on", True)


@HUB_DB
def test_the_list_says_why_an_app_on_cannot_go_off(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: "Tasks are open.", raising=False)
    set_rows(task="on*", staff="on", flow="on*")

    apps_ = by_id(app_list())

    assert apps_["task"]["refusal"] == "Tasks are open."
    assert apps_["staff"]["refusal"] == "Staff can't be turned off: Tasks needs it. Tasks are open."
    assert apps_["flow"]["refusal"] is None


@HUB_DB
def test_the_list_says_why_what_would_go_off_along_keeps_an_app_on(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("staff"), "can_disable", lambda ctx: "Staff is busy.", raising=False)
    set_rows(task="on*", staff="on")

    assert by_id(app_list())["task"]["refusal"] == "Staff is busy."


@HUB_DB
def test_the_list_says_why_an_app_off_cannot_go_on(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("staff"), "can_enable", lambda ctx: "No staff here.", raising=False)
    set_rows(flow="on*")

    apps_ = by_id(app_list())

    assert (apps_["staff"]["state"], apps_["staff"]["refusal"]) == ("off", "No staff here.")
    assert apps_["task"]["refusal"] == "No staff here."  # it would bring Staff along
    assert apps_["flow"]["refusal"] is None


@HUB_DB
def test_the_list_never_asks_the_hook_of_the_other_direction(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: "Tasks are open.", raising=False)
    monkeypatch.setattr(apps.get_app_config("flow"), "can_enable", lambda ctx: "Not here.", raising=False)
    set_rows(task="off", flow="on*")

    apps_ = by_id(app_list())

    assert (apps_["task"]["refusal"], apps_["flow"]["refusal"]) == (None, None)


@HUB_DB
def test_the_list_asks_each_hook_once(monkeypatch):
    calls = []

    def refuse(ctx):
        calls.append(ctx.scope)
        return "Tasks are open."

    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", refuse, raising=False)
    set_rows(task="on*", staff="on")

    app_list()

    assert calls == [A]


@HUB_DB
def test_the_list_says_it_in_the_language_of_who_reads(monkeypatch):
    monkeypatch.setattr(apps.get_app_config("task"), "can_disable", lambda ctx: "Hay tareas abiertas.", raising=False)
    set_rows(task="on*", staff="on")

    apps_ = by_id(app_list(language="es"))

    assert apps_["staff"]["refusal"] == "Personal no se puede desactivar: hace falta para Tareas. Hay tareas abiertas."


@HUB_DB
def test_turning_one_off_and_on_again_keeps_its_data():
    from apps.task.models import Project

    project = Project.objects.create(name="Spring menu")
    set_rows(task="on*", staff="on")
    disable("task")
    assert Project.objects.filter(pk=project.pk).exists()
    enable("task")
    assert Project.objects.get(pk=project.pk).name == "Spring menu"
