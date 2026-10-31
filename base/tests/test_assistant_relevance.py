"""The tools a turn offers for what the owner asks (``live.assistant.relevant`` over the Hub's real catalogue).

The QA battery of the assistant with the real model (2026-10-31, docs/plans/2026-10-31-qa-asistente.md of
erplora-next, block B) found the model answering «I do not have the tool…» for B28, B30 and B32: the owner holds
those operations, but the turn never offered them, because the words asked («empleado», «vendí», «activa la app»)
shared none with the tool's own. Business ``a`` has every module on (``base.activation.every_on``): the largest
catalogue an owner can have, a restaurant's (sale, staff, customer, inventory, cash register, tables, reservations…)
included, so a tool found here is found in any business with fewer apps on.
"""

import pytest
from live.context import OperationContext, Scope

from base import assistant
from base.models import Membership
from base.permissions import permissions_for

A = Scope("host", "a")


@pytest.fixture
def owner(make_user):
    user = make_user("olga", host=A.key, role=Membership.Role.OWNER)

    def of(language: str) -> OperationContext:
        return OperationContext(scope=A, actor="olga", permissions=permissions_for(user, A), language=language)

    return of


def offered(ctx: OperationContext, *asked: str) -> list[str]:
    return [op.name for op in assistant.relevant(assistant.catalog(ctx), list(asked), ctx.language)]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    ("language", "asked", "expected"),
    [
        # B30: «No tengo la herramienta para crear empleados desde aquí».
        ("es", "Da de alta al empleado «Luis QA» como cajero", "staff.member.create"),
        ("en", "Add the employee «Luis QA» as a cashier", "staff.member.create"),
        # B32: «No tengo acceso a los datos de ventas desde aquí».
        ("es", "¿Qué vendí hoy?", "sale.sale.today"),
        ("en", "What did I sell today?", "sale.sale.today"),
        # B28: «Desde aquí no puedo activar apps directamente».
        ("es", "Activa la app de clientes", "base.app.enable"),
        ("en", "Turn on the customers app", "base.app.enable"),
    ],
)
def test_the_tool_that_does_what_the_owner_asks_is_offered(owner, language, asked, expected):
    ctx = owner(language)
    assert expected in assistant.catalog(ctx)  # the owner holds it: only the selection can leave it out
    assert expected in offered(ctx, asked)


#: Block B of the battery, in order: each question with the operations its turn must offer (B1 asks how something is
#: done: the documentation search; B2 asks to do it: the operation that does it, and the read that finds the record).
BLOCK_B = [
    ("¿Cómo doy de alta a un empleado con su PIN?", {"base.docs.search"}),
    ("¿Cómo creo un producto con IVA del 10 %?", {"base.docs.search"}),
    ("¿Cómo hago una venta y cobro en efectivo?", {"base.docs.search"}),
    ("¿Cómo imprimo un ticket?", {"base.docs.search"}),
    ("¿Cómo abro y cierro la caja?", {"base.docs.search"}),
    ("¿Cómo reservo una mesa?", {"base.docs.search"}),
    ("¿Cómo exporto a SAP?", {"base.docs.search"}),
    ("Activa la app de clientes", {"base.app.enable"}),
    ("Crea el cliente «Ana QA» con teléfono 600000000", {"customer.customer.create"}),
    ("Da de alta al empleado «Luis QA» como cajero", {"staff.member.create"}),
    ("Crea el producto «Café QA» a 1,50 € con IVA 10 %", {"inventory.product.create"}),
    ("¿Qué vendí hoy?", {"sale.sale.today"}),
    ("Borra el cliente «Ana QA»", {"customer.customer.delete", "customer.customer.list"}),
    ("¿Cuánto pago a ERPlora al mes?", {"base.docs.search", "base.business.get"}),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("index", "asked", "expected"), [(i, q, e) for i, (q, e) in enumerate(BLOCK_B)])
def test_each_question_of_the_qa_battery_is_offered_its_tools(owner, index, asked, expected):
    ctx = owner("es")
    assert expected <= set(assistant.catalog(ctx))  # the owner holds them: only the selection can leave one out
    # A turn ranks by the last two questions of the person (``base.assistant.turn``): the battery asks them in order.
    before = BLOCK_B[index - 1][0] if index else None
    for texts in ([asked], [before, asked] if before else [asked]):
        missing = expected - set(offered(ctx, *texts))
        assert not missing, (texts, missing)
