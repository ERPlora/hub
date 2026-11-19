"""What the tests of the Hub's assistant share: the person who asks and how the data of a card read back."""

from live.context import OperationContext

from base.tenancy.tests.business import A

MANAGER = frozenset({"base.view_home", "demo.*"})
EMPLOYEE = frozenset({"base.view_home", "demo.view"})


def ctx(permissions=MANAGER, *, actor="ana", language="en", scope=A):
    return OperationContext(scope=scope, actor=actor, permissions=frozenset(permissions), language=language)


def titled(fields: list[dict]) -> dict[str, bool]:
    return {field["name"]: field.get("titled", False) for field in fields}


def shown(fields: list[dict]) -> list[tuple]:
    return [(field["name"], field["kind"], field["value"]) for field in fields]
