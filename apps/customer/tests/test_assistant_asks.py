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


#: What the owner or a manager asks about a customer's orders, with the tool of Customers that answers it: its own asks
#: and phrases nobody wrote yet. With every app on, these tools tied on the tenth place with other apps' order tools and
#: got in only by name (hub#594): one more phrase about «pedido» elsewhere left them out.
ORDER_ASKS = [
    ("en", "customer.order.list", "what orders does Pedro have?"),
    ("en", "customer.order.list", "show me Pedro's orders"),
    ("es", "customer.order.list", "¿qué pedidos tiene el cliente Pedro?"),
    ("es", "customer.order.list", "¿qué pedidos ha hecho Ana?"),
    ("en", "customer.order.customer", "who's on this order?"),
    ("en", "customer.order.customer", "which customer is this order for?"),
    ("es", "customer.order.customer", "¿de quién es este pedido?"),
    ("es", "customer.order.customer", "¿a qué cliente pertenece este pedido?"),
]
#: The first places a turn offers that these tools come within: three short of the QA's first ten
#: (``base/tests/test_assistant_asks.py``), so three more tools may climb past them, or tie with them and go first by
#: name, before they are left out.
WITH_ROOM = 7


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.MANAGER])
@pytest.mark.parametrize(("language", "name", "phrase"), ORDER_ASKS)
def test_a_customers_orders_bring_the_tool_of_customers_with_room_to_spare(catalog_of, role, language, name, phrase):
    tools = catalog_of(role, language)
    assert name in tools  # positive control: the role holds the tool, so its place is known
    offered = [op.name for op in assistant.relevant(tools, [phrase], language)]
    assert name in offered[:WITH_ROOM], (offered.index(name) + 1 if name in offered else None, offered[:WITH_ROOM])
