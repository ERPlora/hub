"""The tools a turn offers for what the owner asks (``live.assistant.relevant`` over the Hub's real catalogue).

The QA battery of the assistant with the real model (2026-10-31, docs/plans/2026-10-31-qa-asistente.md of
erplora-next, block B) found the model answering «I do not have the tool…» for B28, B30 and B32: the owner holds
those operations, but the turn never offered them, because the words asked («empleado», «vendí», «activa la app»)
shared none with the tool's own. Business ``a`` has every module on (``base.activation.every_on``): the largest
catalogue an owner can have, a restaurant's (sale, staff, customer, inventory, cash register, tables, reservations…)
included, so a tool found here is found in any business with fewer apps on.
"""

import pytest
from live import assistant as shared
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


#: What the review of live#18 asked besides the battery: each question with the tool that obviously does it. The Hub
#: has no tool that invites someone (that is done on erplora.com): «invita a…» gets the people of the business, which
#: says how each one gets in, and the documentation search.
EVERYDAY = [
    ("es", "cobra la mesa 4", {"sale.sale.complete"}),
    ("es", "¿cuántos clientes tengo?", {"customer.customer.list", "customer.customer.stats"}),
    ("es", "cambia el precio del café a 1,80", {"inventory.product.update", "pricing.price_item.update"}),
    ("es", "imprime el ticket de la última venta", {"sale.sale.print"}),
    ("es", "dame las reservas de mañana", {"reservation.reservation.list"}),
    ("es", "abre la caja con 100 €", {"cash_register.session.open"}),
    ("es", "añade a Ana como camarera", {"staff.member.create"}),
    ("es", "¿qué productos están sin stock?", {"inventory.product.list_low_stock", "inventory.stock.get_summary"}),
    ("es", "invita a juan@x.com", {"base.person.list", "base.docs.search"}),
    ("es", "desactiva la app de reservas", {"base.app.disable"}),
    ("en", "create a 10% discount", {"pricing.rule.create"}),
    ("en", "show today's takings", {"sale.sale.today"}),
    ("es", "reserva una mesa para 4 personas", {"reservation.reservation.create"}),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "asked", "expected"), EVERYDAY)
def test_an_everyday_request_is_offered_the_tool_that_does_it(owner, language, asked, expected):
    ctx = owner(language)
    assert expected <= set(assistant.catalog(ctx))  # the owner holds them: only the selection can leave one out
    got = offered(ctx, asked)
    assert not expected - set(got), expected - set(got)


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_the_people_of_a_reservation_never_bring_the_staffs_tools(owner):
    """«personas» is not «Personal» (the staff app in Spanish): before live#18's review, «reserva una mesa para 4
    personas» filled the turn with 11 tools of staff and left the reservation's own at 16."""
    got = offered(owner("es"), "reserva una mesa para 4 personas")
    assert got.index("reservation.reservation.create") == len(assistant.ALWAYS)  # first after what is always at hand
    assert sum(name.startswith("staff.") for name in got) <= 1, [name for name in got if name.startswith("staff.")]


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


#: The Hub's own words (``base.assistant.SYNONYMS``), in phrases no tool says as its asks: a «cuenta», a check or a
#: tab is a table's open check (``sale.order``), never the person's account; a ticket or a receipt is a sale's.
HUB_WORDS = [
    ("es", "¿qué hay en la cuenta de la mesa 6?", "sale.order.get"),
    ("es", "divide la cuenta de la mesa 2 entre tres", "sale.order.split"),
    ("en", "what's on the tab for table 6?", "sale.order.get"),
    ("es", "reimprime el ticket 25", "sale.sale.print"),
    ("es", "¿de cuánto fue el ticket 25?", "sale.sale.get"),
    ("en", "show me ticket 25", "sale.sale.get"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "asked", "expected"), HUB_WORDS)
def test_the_hubs_own_words_bring_the_tool_they_mean_among_the_first_ten(owner, language, asked, expected):
    """Before the Hub said what its words mean, these came at 11 to 31, or not at all: «cuenta» shared no word with an
    order and «ticket» brought the kitchen's tickets (live#22 leaves those meanings to each project)."""
    ctx = owner(language)
    assert expected in assistant.catalog(ctx)  # the owner holds it: only the selection can leave it out
    assert expected in offered(ctx, asked)[:10]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    ("language", "asked"), [("es", "¿cómo invito a alguien a mi negocio?"), ("en", "how do I split a check?")]
)
def test_a_how_to_question_ranks_the_documentation_first_by_being_one(owner, language, asked):
    """The documentation search is always offered (``ALWAYS``), and a how-to question also ranks it first by itself
    (``HOWTO``): ranked without what is always at hand, it still leads."""
    tools = assistant.catalog(owner(language))
    ranking = {**assistant.RANKING, "always": ()}
    assert [op.name for op in shared.relevant(tools, [asked], language, **ranking)][0] == assistant.DOCS_SEARCH
