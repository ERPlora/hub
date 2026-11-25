"""What layer 1 of the assistant's QA does not say of Cash register: how many tools it offers, that the requests of
the real-model QA (hub#1087), in the words the person said them, are offered their existing operation, and with it
the read it needs first, and that no description makes the model stop in the chat before a write's card (hub#1138).

Every ask of every tool of cash_register bringing its tool among the first ten, role by role, in both languages, is
``base/tests/test_assistant_asks.py``'s (cash_register is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020``
over the asks and the guard that no ask copies a probe of layer 2.
"""

import re

import pytest
from django.apps import apps
from live import assistant as shared
from live.operations import AI, Operation, registry

from apps.cash_register.tests.conftest import HUB_DB
from apps.invoice.tests.conftest import in_hubs
from base import assistant
from base.models import Membership
from base.tests.roles import WORKING_ROLES
from base.tests.test_assistant_asks import (
    assert_its_words_name,
    TOP,
    assert_offered_with_room,
    by_group_test,
    comparable,
    offered_to,
    place_of_no_ask,
    probe_phrases,
)

OWNER, EMPLOYEE = Membership.Role.OWNER, Membership.Role.EMPLOYEE

#: The requests of hub#1087's QA (``tests/e2e/qa/probes/*-es-cash_register-2026-11-08.json``), as each role said them:
#: before Cash register said its asks, the first four were offered no tool of the drawer (the model answered it had no
#: tool, or looked for an automation) and the print was offered without the read that finds the open shift (the model
#: asked for the session's number). The employee's close was already offered (4th), its summary too: the model read the
#: summary, told it and waited, because the descriptions said «tell the person its summary, then close» (hub#1138,
#: ``test_no_tool_of_cash_register_makes_the_model_stop_in_the_chat_before_its_card``).
REPORTED = [
    (OWNER, "cash_register.count.list", "¿qué recuentos de monedas y billetes se han registrado en el turno abierto?"),
    (
        OWNER,
        "cash_register.session.get",
        "pásame el informe completo del turno abierto, con fondo, ventas, movimientos y diferencia",
    ),
    (
        OWNER,
        "cash_register.count.add",
        "registra un recuento de apertura en Barra QA: tres billetes de 50 € y veinte monedas de 1 €, con nota "
        "«comprobado QA»",
    ),
    (
        OWNER,
        "cash_register.session.auto_close",
        "ejecuta ahora el cierre automático diario por si hubiera algún turno antiguo que ya hubiera pasado la hora de "
        "corte",
    ),
    (
        OWNER,
        "cash_register.session.print",
        "imprime el informe X del turno abierto de Barra QA con las ventas y los movimientos hasta ahora",
    ),
    (
        EMPLOYEE,
        "cash_register.session.close",
        "cierra la sesión S-261109-0001 con 170 € contados y la nota «cierre de empleado QA», mostrándome antes el "
        "resumen",
    ),
]
#: The read each reported request needs before its tool: a session said as «el turno abierto» is found by
#: ``cash_register.session.current`` (the report, its counts and its print take the session's id or number), and the
#: close is said after ``cash_register.session.closing_summary`` (its description asks to read it first).
FIRST = {
    "cash_register.count.list": "cash_register.session.current",
    "cash_register.session.get": "cash_register.session.current",
    "cash_register.session.print": "cash_register.session.current",
    "cash_register.session.close": "cash_register.session.closing_summary",
}
#: The role of a probe as its id says it (``qa20261108.<role>.es.<tool>``).
PROBE_ROLE = {OWNER: "owner", EMPLOYEE: "employee"}


def test_cash_register_offers_at_least_19_tools():
    """Cash register's tools are at least 19 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {name for name, op in registry.items() if op.app_label == "cash_register" and isinstance(op.ai_spec(), AI)}
    assert len(tools) >= 19


def test_the_reported_requests_are_the_probes_of_layer_2():
    phrases = probe_phrases()
    assert [phrases.get(comparable(phrase)) for _, _, phrase in REPORTED] == [
        f"qa20261108.{PROBE_ROLE[role]}.es.{name}" for role, name, _ in REPORTED
    ]


def test_the_hub_reads_an_arqueo_as_a_count_and_the_moneda_as_the_currency():
    """Cash register's own words (its ``assistant_synonyms``): an «arqueo», a «recuento» or a «conteo» is a count of the
    drawer (``cash_register.count``) and the «moneda» or the «divisa» of the business its currency
    (``cash_register.currency``), so the person's words reach those tools without their own asks; without the Hub's
    groups, none does (positive control)."""
    count, currency = shared.stem("count"), shared.stem("currency")
    assert_its_words_name(
        "cash_register",
        [
            ("haz el arqueo del cajón", count),
            ("¿hay algún recuento de cierre?", count),
            ("apunta el conteo de la mañana", count),
            ("¿en qué moneda trabaja el negocio?", currency),
            ("¿cuál es la divisa del negocio?", currency),
        ],
    )


@HUB_DB  # the catalogue is of the apps on in the business (base.activation) and of the person's role
@pytest.mark.parametrize(("role", "name", "phrase"), REPORTED)
def test_the_reported_cash_register_request_offers_its_existing_operation(catalog_of, role, name, phrase):
    assert place_of_no_ask(catalog_of(role, "es"), name, phrase) is not None


#: The task the model searches for when a reported request brings the read it needs first past the places of a turn.
FIRST_SEARCHED = {"cash_register.session.get": "ver el turno de caja abierto"}


@HUB_DB
@pytest.mark.parametrize(("role", "name", "phrase"), [case for case in REPORTED if case[1] in FIRST])
def test_the_reported_request_is_offered_the_read_it_needs_first(catalog_of, role, name, phrase):
    tools = catalog_of(role, "es")
    assert FIRST[name] in tools  # positive control: the role holds the read
    offered = offered_to(tools, phrase)
    task = FIRST_SEARCHED.get(name)
    found = [op.name for op in assistant.relevance.found(tools, task, "es")] if task else []
    assert FIRST[name] in offered + found, (len(offered), offered[:10])


#: Money coming into the drawer said as a business says it, in words that are none of the tool's asks nor a probe:
#: «entran» with an amount is cash in the till, not goods received (the Hub's delivery-note group also holds «entran»).
MONEY_IN = [("cash_register.movement.add", "registra que entran 100 € en el turno")]
#: Money taken out said as «una salida» of an amount already brings the movement among the first ten without the
#: Hub's group of movements, with or without the shift it goes in: the group keeps it there.
MONEY_OUT = [
    ("cash_register.movement.add", "apúntame una salida de 50 €"),
    ("cash_register.movement.add", "mete una salida de 20 € en el turno"),
]


@HUB_DB
@pytest.mark.parametrize(("name", "phrase"), MONEY_IN + MONEY_OUT)
def test_money_coming_in_or_going_out_in_the_hubs_words_brings_the_movement_among_the_first_ten(
    catalog_of, name, phrase
):
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(catalog_of(OWNER, "es"), name, phrase, room=TOP)


#: A movement of the drawer said as a business says it, «una entrada», «una salida» or «un movimiento» of an amount,
#: with or without the shift it goes in, by «apunta», «anota» or «mete». The tool's asks say neither «entrada» nor
#: «movimiento», so without the group none of these is among the first ten: shift and staff settings came first.
MOVEMENT_SAID = [
    ("cash_register.movement.add", "apúntame una entrada de 50 € de cambio en el turno", "una entrada"),
    ("cash_register.movement.add", "apúntame una entrada de 50 €", "una entrada"),
    ("cash_register.movement.add", "anota en el turno una entrada de 50 € de cambio", "una entrada"),
    ("cash_register.movement.add", "mete una entrada de 50 € en el turno", "una entrada"),
    ("cash_register.movement.add", "mete una entrada de 50 €", "una entrada"),
    ("cash_register.movement.add", "apúntame una salida de 50 € en el turno", "una salida"),
    ("cash_register.movement.add", "apúntame un movimiento de 50 € en el turno", "un movimiento"),
]

test_a_movement_said_as_a_business_says_it_brings_its_tool_by_cash_registers_group = in_hubs(
    by_group_test(MOVEMENT_SAID)
)

#: «Entrada» and «salida» said of anything but the drawer's money: a clock-in or a clock-out, goods received, a place
#: in the waiting list, what left the kitchen's pass. A bare «entrada» also shares its stem with «entre» and «entra».
OTHER_ENTRIES = [
    "ficha mi salida",
    "registra mi entrada",
    "apunta la salida de Ana a las 18:00",
    "registra la entrada de mercancía del albarán de hoy",
    "han entrado 12 unidades de tarta",
    "abre la entrada de Ana en la lista de espera",
    "la 12 ya ha salido del pase",
    "ventas entre el lunes y el viernes",
]


def test_the_hub_reads_una_entrada_una_salida_or_un_movimiento_as_a_movement_and_no_other_entry():
    """Cash register's own words (its ``assistant_synonyms``): «una entrada», «una salida» or «un movimiento», also
    after «otra» or «otro», is a movement of the drawer (``cash_register.movement``), and without the Hub's groups
    none is (positive control); the other senses of «entrada» and «salida» name no movement."""
    movement = shared.stem("movement")
    assert_its_words_name(
        "cash_register",
        [
            ("apúntame una entrada de 50 € de cambio en el turno", movement),
            ("registra una salida de 15 € para hielo en el turno", movement),
            ("apúntame un movimiento de 50 € en el turno", movement),
            ("apunta otra entrada de 20 € en la caja", movement),
            ("anota otra salida de 10 € para hielo", movement),
            ("anota otro movimiento de 10 € en la caja", movement),
        ],
    )
    own = apps.get_app_config("cash_register").assistant_synonyms
    named = [said for said in OTHER_ENTRIES if any(movement in one for one in shared.asked([said], own).concepts)]
    assert named == []


#: Several movements said by how many come before their amount: «dos entradas de 20 €», «2 salidas de 10 €», «two
#: entries of 20 €». Main offered the movement 58th for the first one and 167th for «two entries of 20 €», behind the
#: staff's shifts: no phrase of the group said a count. «log 3 cash outs of 10 €» already came 5th, by «cash».
SEVERAL_MOVEMENTS_SAID = [
    ("es", "apúntame dos entradas de 20 € en el turno"),
    ("es", "anota 2 entradas de 50 € en el turno"),
    ("es", "apúntame dos salidas de 10 € en el turno"),
    ("es", "apúntame cuatro entradas de 10 € en el turno"),
    ("es", "apúntame dos movimientos de 20 € en el turno"),
    ("en", "two entries of 20 €"),
    ("en", "record three entries of 10 € in the shift"),
    ("en", "log 3 cash outs of 10 €"),
]


@HUB_DB
@pytest.mark.parametrize("role", WORKING_ROLES)
@pytest.mark.parametrize(("language", "phrase"), SEVERAL_MOVEMENTS_SAID)
def test_several_movements_said_by_their_count_bring_the_movement_among_the_first_ten(
    catalog_of, role, language, phrase
):
    assert comparable(phrase) not in probe_phrases()
    assert_offered_with_room(catalog_of(role, language), "cash_register.movement.add", phrase, language, room=TOP)


test_several_movements_said_by_their_count_bring_their_tool_by_cash_registers_group = in_hubs(
    by_group_test(
        [
            ("cash_register.movement.add", "apúntame dos entradas de 20 € en el turno", "dos entradas de"),
            ("cash_register.movement.add", "anota 2 entradas de 50 € en el turno", "2 entradas de"),
            ("cash_register.movement.add", "apúntame dos movimientos de 20 € en el turno", "dos movimientos de"),
        ]
    )
)

#: Every count the group says, in words and in figures, before each kind of movement.
COUNTS = {
    "es": ("dos", "tres", "cuatro", "cinco", "2", "3", "4", "5"),
    "en": ("two", "three", "four", "five", "2", "3", "4", "5"),
}
COUNTED_SAID = [
    *(
        f"apúntame {count} {kind} de 20 € en el turno"
        for count in COUNTS["es"]
        for kind in ("entradas", "salidas", "movimientos")
    ),
    *(f"record {count} entries of 20 € in the shift" for count in COUNTS["en"]),
]
#: «Entradas» and «entries» of anything but the drawer's money, said without a count, or with one but not before «de»
#: or «of»: tickets of a concert, places in the waiting list, goods received. A bare «entradas» shares its stem with
#: «entre» and «entra», and a bare «entries» names the waiting list's.
OTHER_COUNTED = [
    "vende dos entradas para el concierto",
    "¿cuántas entradas del concierto quedan?",
    "apunta dos entradas en la lista de espera para esta noche",
    "registra las entradas de mercancía del albarán de hoy",
    "¿a qué hora entra Ana?",
    "ventas entre el lunes y el viernes",
    "add two entries to the waitlist for tonight",
    "delete two entries from the waitlist",
    "show the entries of the waitlist",
]


def test_the_hub_reads_a_count_of_entradas_salidas_or_movimientos_before_their_amount_as_movements():
    """Cash register's own words (its ``assistant_synonyms``): a count of «entradas», «salidas» or «movimientos» said
    before «de», or of «entries» before «of», is movements of the drawer (``cash_register.movement``), and without the
    Hub's groups none is (positive control); the other senses of «entradas» and «entries» name no movement."""
    movement = shared.stem("movement")
    assert_its_words_name("cash_register", [(said, movement) for said in COUNTED_SAID])
    own = apps.get_app_config("cash_register").assistant_synonyms
    named = [said for said in OTHER_COUNTED if any(movement in one for one in shared.asked([said], own).concepts)]
    assert named == []


#: The tills of a place said as «las cajas de la tienda»: Inventory reads «cajas de» as boxes of goods, so without Cash
#: register's own phrase the stock's tools came before the list of the tills (12th).
TILLS_SAID = [("cash_register.register.list", "¿qué cajas de la tienda hay dadas de alta?", "cajas de la")]

test_the_tills_of_a_place_bring_their_list_by_cash_registers_group = in_hubs(by_group_test(TILLS_SAID))


def test_the_hub_reads_las_cajas_de_la_tienda_as_its_tills():
    """Cash register's own words (its ``assistant_synonyms``): «las cajas de la» barra, terraza or tienda are the tills
    (``cash_register.register``), and without the Hub's groups they are not (positive control); boxes of goods are not
    tills."""
    register = shared.stem("register")
    assert_its_words_name(
        "cash_register",
        [("¿qué cajas de la tienda hay dadas de alta?", register), ("cierra las cajas de la terraza", register)],
    )
    own = apps.get_app_config("cash_register").assistant_synonyms
    boxes_of_goods = ["registra una entrada de 5 cajas de leche", "han llegado 4 cajas de cerveza"]
    assert [said for said in boxes_of_goods if any(register in one for one in shared.asked([said], own).concepts)] == []


#: What makes the model answer in the chat and wait, so the card of a write never comes (hub#1105, hub#1138): a
#: description that tells it to ask first, or to tell the person something and only then run the write (the employee's
#: close stopped at its summary: «tell the person its summary, then close»). Whatever it tells the person before a
#: write goes in the same answer as the write's call: the panel shows that text, then the card, where the person says yes.
ASK_FIRST = re.compile(r"\bask\b[^.]*\b(?:first|before)\b", re.IGNORECASE)
TELL = re.compile(r"\btell the person\b", re.IGNORECASE)
SAME_ANSWER = re.compile(r"\bin the same answer\b", re.IGNORECASE)


def stops_in_the_chat(description: str) -> list[str]:
    """The sentences of ``description`` that make the model stop in the chat before a write's card."""
    sentences = re.split(r"(?<=[.;])\s+", description)
    return [said for said in sentences if ASK_FIRST.search(said) or (TELL.search(said) and not SAME_ANSWER.search(said))]


def cash_register_tools() -> dict[str, Operation]:
    return {name: op for name, op in registry.items() if op.app_label == "cash_register" and assistant.tools.is_tool(op)}


def test_no_tool_of_cash_register_makes_the_model_stop_in_the_chat_before_its_card():
    # Positive controls: the close's and its summary's texts before hub#1138, and the «ask first» of hub#1105.
    assert stops_in_the_chat("Read the summary first, tell the person its summary, then close naming the session.")
    assert stops_in_the_chat("Changes nothing. Read it before closing and tell the person this summary; with none, no.")
    assert stops_in_the_chat("Its drawer is freed. Always ask the person before.")
    assert not stops_in_the_chat("In the same answer where you tell the person its summary, call this tool.")
    assert not stops_in_the_chat("With the count required and none said, it asks for the count.")
    told = {name: stops_in_the_chat(shared.description(op)) for name, op in cash_register_tools().items()}
    assert {name: said for name, said in told.items() if said} == {}


def test_the_close_goes_in_the_same_answer_that_tells_its_summary():
    """The read before the close sends the model on to the close, and the close says when to call it: in the answer
    that tells the summary, never after the person answers it (its card is the confirmation, CASH_REGISTER-F09)."""
    tools = cash_register_tools()
    close = shared.description(tools["cash_register.session.close"])
    summary = shared.description(tools["cash_register.session.closing_summary"])
    assert "cash_register.session.closing_summary" in close
    assert SAME_ANSWER.search(close)
    assert "cash_register.session.close " in summary or "cash_register.session.close:" in summary
    assert SAME_ANSWER.search(summary)
