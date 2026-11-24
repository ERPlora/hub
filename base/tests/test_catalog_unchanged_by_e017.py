"""The assistant's catalogue did not move when ``ai=`` became typed and mandatory (``live.E017``).

Before, the Hub decided a tool by the words of an ``ai=`` dictionary and by its permission: no description, «Not an
assistant tool…»/«System only…», no permission or one no app declares (the platform's reactions and scheduled tasks)
and what is never done from the chat (``NOT_FROM_CHAT``) were no tool. Now ``live.assistant`` decides by
``Operation.ai_spec()`` (``AI`` or ``INTERNAL``) and the operations that declared nothing say ``INTERNAL``.
``legacy_catalog`` is that rule by the words: an owner, a manager, an employee and a superuser are offered exactly the
tools it gives them, in the same order. Of the assistant's own operations only the search of the tools is left out by
its name, as every turn offers it apart; the rest say by their words whether they are a tool.
"""

import pytest
from live.context import OperationContext
from live.meta import all_live_app_configs
from live.operations import AI, Operation, registry

from base import approvals, assistant
from base.models import Membership
from base.permissions import access_for
from base.tenancy.tests.business import HUB_DB, A, in_business_a

#: Business A, entered for every test with its own database (``in_business_a``).
__all__ = ["in_business_a"]

#: The words a dictionary started with to say it was no tool, and what was never done from the chat, as they were.
LEGACY_NOT_A_TOOL = ("Not an assistant tool", "System only")
LEGACY_NOT_FROM_CHAT = frozenset({"base.hub.reset", "base.blueprint.export"})


def legacy_declaration(op: Operation) -> dict:
    """``op``'s ``ai=`` as the old rule read it: a dictionary; a typed tool as the dictionary it stands for."""
    if isinstance(op.ai, dict):
        return op.ai
    if isinstance(op.ai, AI):
        return {"description": op.ai.description, "risk": op.ai.risk}
    return {}


def legacy_is_tool(op: Operation, declared_permissions: frozenset[str]) -> bool:
    text = str(legacy_declaration(op).get("description", "")).strip()
    return (
        bool(text)
        and op.permission is not None
        and op.permission in declared_permissions
        and not text.startswith(LEGACY_NOT_A_TOOL)
        and op.name not in LEGACY_NOT_FROM_CHAT
        and op.name != "base.assistant.find_tools"
    )


def legacy_catalog(ctx: OperationContext) -> list[str]:
    declared = frozenset(permission for config in all_live_app_configs() for permission in config.permissions)
    on = assistant.tools.active_apps(ctx.scope)
    return [
        name
        for name, op in sorted(registry.items())
        if op.app_label in on
        and legacy_is_tool(op, declared)
        and (ctx.has(op.permission) or approvals.label_of(op) is not None)
    ]


def person(user) -> OperationContext:
    return OperationContext(scope=A, actor=user, permissions=access_for(user, A), language="es")


@HUB_DB
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.EMPLOYEE])
def test_a_person_of_the_business_is_offered_the_same_tools(make_user, role):
    ctx = person(make_user("eva", host=A.key, role=role))
    expected = legacy_catalog(ctx)
    assert expected  # not an empty sweep
    assert list(assistant.tools.catalog(ctx)) == expected


@HUB_DB
def test_a_superuser_is_offered_the_same_tools_and_none_only_the_platform_runs(superuser):
    """«*» reaches every permission: only the old rule of the platform's permissions kept their reactions out. Said
    outright: a superuser holds «*» on the platform's scope alone, nothing on a business's host (``base.permissions``)."""
    ctx = OperationContext(scope=A, actor=superuser, permissions=frozenset({"*"}), language="es")
    expected = legacy_catalog(ctx)
    assert expected and "demo.item.create" in expected  # «*» reached a write no approval offers: not an empty sweep
    assert "table.hold.expire" not in expected and "staff.member.current" not in expected
    assert list(assistant.tools.catalog(ctx)) == expected
