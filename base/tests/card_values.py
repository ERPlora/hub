"""What the tests of the values on the assistant's card share."""

import datetime as dt
from typing import Literal
from uuid import UUID

from django.core import checks
from live.context import OperationContext, Scope
from live.operations import Operation, registry
from ninja import Schema

from base import assistant

A = Scope("host", "a")
ADMIN = frozenset({"base.view_home", "base.administer_hub"})


def ctx(permissions=ADMIN, *, actor="ana", language="es") -> OperationContext:
    return OperationContext(scope=A, actor=actor, permissions=frozenset(permissions), language=language)


def values(card: dict) -> dict:
    return {field["name"]: field["value"] for field in card["fields"]}


class VisitIn(Schema):
    staff_id: UUID
    start: dt.datetime
    source: Literal["counter", "phone"]


def writes() -> list[Operation]:
    return [op for _, op in sorted(registry.items()) if op.kind == "command" and assistant.tools.is_tool(op)]


def reference_errors() -> list:
    return [error for error in checks.run_checks(tags=["base"]) if error.id == "base.E009"]


def is_attempt_key(prop: dict) -> bool:
    return prop.get("attempt_key") is True
