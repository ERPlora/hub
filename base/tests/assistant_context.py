"""What the tests of the Hub's assistant share: the person who asks, the tools a turn offers them and how the data of
a card read back."""

from live.context import OperationContext
from live.operations import get

from base.models import Membership
from base.permissions import permissions_for
from base.tenancy.tests.business import A

MANAGER = frozenset({"base.view_home", "demo.*"})
EMPLOYEE = frozenset({"base.view_home", "demo.view"})


def ctx(permissions=MANAGER, *, actor="ana", language="en", scope=A):
    return OperationContext(scope=scope, actor=actor, permissions=frozenset(permissions), language=language)


def owner_of_a(make_user, language: str = "es") -> OperationContext:
    """The owner of business A talking to the assistant in ``language``, with the permissions their role holds."""
    user = make_user("olga", host=A.key, role=Membership.Role.OWNER)
    return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language=language)


def offered(ctx: OperationContext, *messages: dict) -> list[str]:
    """The tools a turn of the assistant offers ``ctx`` for the conversation ``messages``, by their tool names."""
    op = get("base.assistant.turn")
    plan = op(ctx, op.input(messages=list(messages))).model_dump(mode="json")
    return [tool["name"] for tool in plan["tools"]]


def titled(fields: list[dict]) -> dict[str, bool]:
    return {field["name"]: field.get("titled", False) for field in fields}


def shown(fields: list[dict]) -> list[tuple]:
    return [(field["name"], field["kind"], field["value"]) for field in fields]
