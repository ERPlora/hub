"""The tools of the Hub's assistant (``base/assistant/tools.py``, ``base/assistant/relevance.py``): which
operations are its tools for this person, the few it offers in a turn, and how a tool runs as the person."""

import json

import pytest
from django.utils import translation
from live import assistant as shared
from live.context import OperationContext
from live.operations import NOT_A_TOOL, get, registry

from base import assistant, entitlement
from base.models import Membership
from base.permissions import access_for
from base.tenancy.tests.business import HUB_DB, A, in_business_a
from base.tests.assistant_context import EMPLOYEE, MANAGER, ctx

__all__ = ["in_business_a"]


# ── Tools: what the assistant may use for this person ────────────────────────────────────────────────────────────


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_a_tool_is_named_without_dots_and_read_back_from_its_name():
    assert shared.tool_name("cash_register.session.close") == "cash_register__session__close"
    tools = assistant.tools.catalog(ctx({"*"}))
    assert shared.operation_of("demo__item__create", tools).name == "demo.item.create"
    assert shared.operation_of("demo__item__nothing", tools) is None


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_tools_are_the_operations_this_person_may_use_and_nothing_else():
    names = set(assistant.tools.catalog(ctx(EMPLOYEE)))
    assert "demo.item.list" in names
    # Without «demo.manage» the write is not even offered (the old hub's: as if it did not exist).
    assert "demo.item.create" not in names
    assert "base.access.settings_update" not in names


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    "name, why",
    [
        ("base.pin.set", "«Not an assistant tool»: a PIN is typed on the pad"),
        ("base.hub.reset", "never from the chat: it empties the business"),
        ("base.blueprint.export", "never from the chat: a file to download"),
        ("base.app.list", "no description for the assistant"),
        ("base.demo.create", "the system's (no permission declared)"),
    ],
)
def test_what_is_not_a_tool_is_never_offered_even_to_who_may_do_everything(name, why):
    assert name not in assistant.tools.catalog(ctx({"*"})), why


def test_no_description_written_for_the_model_is_dropped_for_want_of_a_permission():
    """An ``ai=`` dictionary that describes a tool on an operation with no permission is read as no tool
    (``Operation.ai_spec``), so the model never sees what was written for it: a read the assistant needs, such as the
    accounts a staff record can hang from, is left without a way in. It says it is no tool, or it gets a permission."""
    open_ops = [op for op in registry.values() if op.permission is None]
    assert any(isinstance(op.ai, dict) for op in open_ops)  # not an empty sweep
    dropped = sorted(
        op.name
        for op in open_ops
        if isinstance(op.ai, dict)
        and str(op.ai.get("description", "")).strip()
        and not str(op.ai["description"]).strip().startswith(NOT_A_TOOL)
    )
    assert dropped == []


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_an_app_the_business_has_no_right_to_offers_no_tool(monkeypatch):
    monkeypatch.setattr(entitlement, "blocked_apps", lambda scope: frozenset({"demo"}))
    assert not [name for name in assistant.tools.catalog(ctx({"*"})) if name.startswith("demo.")]


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_assistants_own_operations_are_not_its_tools_but_the_months_messages():
    """Its turn, a report, a dictation, reading aloud and the search of the rest run apart from its tools; this month's
    messages are a read the person may ask for, as «Usage and plan» shows them."""
    own = [name for name in assistant.tools.catalog(ctx({"*"})) if name.startswith("base.assistant.")]
    assert own == ["base.assistant.usage"]


#: Writes only the platform runs, of both shapes their permission takes (``<app>.system``, ``system.<app>``), each with
#: an ``ai=`` that does not start with «System only»: «Platform reaction…», «Platform only…», «Lower the stock…».
PLATFORM_WRITES = {
    "appointment.customer.erase", "online_booking.customer.erase", "table.hold.expire", "inventory.stock.apply_sale",
    "service.grant.reassign",
}


def platform_operations(owner: OperationContext) -> list[str]:
    """The operations only who holds «*» reaches (the system; a superuser, on the platform's scope only): not even the
    owner of the business, who holds every permission its apps declare, may run them."""
    return sorted(name for name, op in registry.items() if op.permission is not None and not owner.has(op.permission))


@pytest.fixture
def owner(make_user) -> OperationContext:
    """The owner of business A with the permissions a request of theirs carries (``base.permissions``)."""
    return ctx(access_for(make_user("olga", host=A.key, role=Membership.Role.OWNER), A))


@HUB_DB
def test_no_operation_of_the_platform_is_a_tool_whatever_its_ai_says(owner):
    """The platform's reactions and scheduled tasks (erasing or reassigning the customer of an appointment, expiring a
    hold, lowering the stock of a sale) must not be tools of whoever holds «*» just because their ``ai=`` does not start
    with «System only». Its permission says so, not its words."""
    platform = platform_operations(owner)
    assert PLATFORM_WRITES <= set(platform)  # not an empty sweep
    assert [name for name in platform if assistant.tools.is_tool(registry[name])] == []


@HUB_DB
def test_a_superusers_assistant_is_offered_no_operation_of_the_platform(owner, superuser):
    """The tools a superuser's turn gets (``base.assistant.turn``: ``catalog`` of the person's own permissions): on a
    business's host those of a person without a role, since ERPlora's staff holds nothing there without a Membership
    (``base.permissions``); and «*» itself offers every write of the business's apps, none that only the platform
    runs."""
    staff_tools = assistant.tools.catalog(ctx(access_for(superuser, A), actor=superuser))
    assert staff_tools == assistant.tools.catalog(ctx(frozenset(), actor=superuser))  # what a person without a role gets
    assert "demo.item.create" not in staff_tools
    tools = assistant.tools.catalog(ctx({"*"}, actor=superuser))
    assert "demo.item.create" in tools
    assert sorted(set(tools) & set(platform_operations(owner))) == []


# ── By relevance: a turn offers the tools of what was asked, never the whole catalogue ────────────────────────────


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_a_turn_offers_at_most_its_share_of_the_catalogue():
    tools = assistant.tools.catalog(ctx({"*"}))
    assert len(tools) > shared.MAX_TOOLS
    assert len(assistant.relevance.relevant(tools, ["hola"], "es")) <= shared.MAX_TOOLS


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_app_named_in_the_persons_own_language_comes_first():
    tools = assistant.tools.catalog(ctx({"*"}))
    offered = assistant.relevance.relevant(tools, ["¿Cuántos clientes tengo este mes?"], "es")
    # After the two reads always at hand (``ALWAYS``), the app the person named.
    first = [op.name for op in offered if op.name not in assistant.relevance.ALWAYS][:5]
    assert first and all(name.startswith("customer.") for name in first), first
    assert "customer.customer.list" in first


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_what_the_person_asks_to_do_ranks_the_operation_that_does_it():
    tools = assistant.tools.catalog(ctx({"*"}))
    offered = [op.name for op in assistant.relevance.relevant(tools, ["crea un servicio Corte caballero a 15 €"], "es")]
    assert "service.service.create" in offered


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_version_of_erplora_is_at_hand_for_who_runs_the_business():
    """Asked «what version of ERPlora do I have?», the assistant has a tool that answers it."""
    tools = assistant.tools.catalog(ctx({"base.view_home", "base.administer_hub"}))
    offered = [op.name for op in assistant.relevance.relevant(tools, ["¿Qué versión de ERPlora tengo?"], "es")]
    assert "base.system.status" in offered
    assert "base.system.status" not in assistant.tools.catalog(ctx(EMPLOYEE))


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_checklist_read_is_always_at_hand():
    tools = assistant.tools.catalog(ctx({"*"}))
    assert "base.setup.status" in [op.name for op in assistant.relevance.relevant(tools, ["zzz"], "es")]


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("permissions", [EMPLOYEE, MANAGER, {"*"}])
def test_the_documentation_search_is_always_at_hand_for_everybody(permissions):
    """Everything it is asked, it answers with our own information, inventing nothing: a how-to question («¿cómo abro
    la caja?») shares no word with the tool, so it is in every turn."""
    assert "base.docs.search" in assistant.relevance.ALWAYS
    tools = assistant.tools.catalog(ctx(permissions))
    assert "base.docs.search" in tools
    assert "base.docs.search" in [op.name for op in assistant.relevance.relevant(tools, ["¿cómo abro la caja?"], "es")]


@pytest.mark.parametrize(("language", "name"), [("en", "Help"), ("es", "Ayuda")])
def test_a_documentation_search_is_named_help_on_its_receipt(language, name):
    """As the panel of erplora.com names it: the help, not a screen of the business."""
    with translation.override(language):
        assert assistant.cards.app_name(get("base.docs.search")) == name


def test_a_tool_is_offered_in_the_gateways_format():
    spec = shared.tool_spec(get("demo.item.create"))
    assert spec["type"] == "function"
    assert spec["name"] == "demo__item__create"
    assert spec["description"].startswith("Creates a demo item")
    assert spec["parameters"]["properties"]["name"]["type"] == "string"


# ── A tool runs as the person, by its own operation ──────────────────────────────────────────────────────────────


@HUB_DB
def test_a_tool_runs_by_its_operation_with_the_persons_permissions():
    outcome = shared.run_tool(ctx(), get("demo.item.create"), '{"name": "Mesa 4"}')
    assert outcome.outcome == "ok"
    created = json.loads(outcome.content)
    listed = shared.run_tool(ctx(EMPLOYEE), get("demo.item.list"), "{}")
    assert created["id"] in listed.content


@HUB_DB
def test_a_tool_the_person_may_not_use_is_refused_and_writes_nothing():
    outcome = shared.run_tool(ctx(EMPLOYEE), get("demo.item.create"), '{"name": "Mesa 4"}')
    assert (outcome.outcome, outcome.code) == ("refused", "permission_denied")
    assert "Mesa 4" not in shared.run_tool(ctx(EMPLOYEE), get("demo.item.list"), "{}").content


@HUB_DB
def test_arguments_that_do_not_fit_come_back_to_the_model_with_the_field():
    outcome = shared.run_tool(ctx(), get("demo.item.create"), '{"name": ""}')
    assert (outcome.outcome, outcome.code) == ("error", "invalid_payload")
    assert "name" in json.loads(outcome.content)["error"]["fields"]
    broken = shared.run_tool(ctx(), get("demo.item.create"), "{not json")
    assert (broken.outcome, broken.code) == ("error", "invalid_payload")
