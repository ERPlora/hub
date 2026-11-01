"""What layer 1 of the assistant's QA does not say of Customers (erplora-next docs/plans/2026-10-31-asistente-
conocimiento-y-qa.md): how many tools it offers, and what an employee is never offered.

Every ask of every tool of customer bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(customer is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks and the place a turn gives
each.
"""

import pytest
from live.context import OperationContext, Scope
from live.operations import AI, Operation, registry

from base import assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")
#: Writes on cards and settings that only the owner and the admin hold, none of them a manager approves: an employee's
#: assistant is never offered them (an approvable write is, as its button on the screen: running it asks a manager).
NOT_THE_EMPLOYEES = {
    "customer.customer.delete",
    "customer.customer.erase",
    "customer.group.delete",
    "customer.tag.delete",
}


@pytest.fixture
def catalog_of(make_user):
    """The real catalogue of the assistant of a person with ``role`` in business ``a``, in ``language``."""

    def of(role: str, language: str) -> dict[str, Operation]:
        user = make_user(f"asker-{role}", host=A.key, role=role)
        ctx = OperationContext(
            scope=A, actor=user.username, permissions=permissions_for(user, A), language=language
        )
        return assistant.catalog(ctx)

    return of


def test_customer_offers_at_least_30_tools():
    """Customer's tools are at least 30 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "customer" and isinstance(op.ai_spec(), AI)}
    assert len(tools) >= 30


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_an_employee_is_never_offered_what_only_the_owner_may_do(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert "customer.customer.create" in employee  # positive control: the employee's own writes are there
