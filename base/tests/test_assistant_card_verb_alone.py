"""The verb of a write whose card comes with no data: its card and its receipt are that verb and its app alone, so the
verb says what the write does, never a verb another write says too.

«Pon que estoy en pausa» drew «Empezar en Control horario.» and its receipt «Hecho: Empezar en Control horario»: whoever
read it could not tell a break from a working day; closing the expired carts said «Clean up the expired in Cart &
Checkout» (hub#2297)."""

from collections.abc import Iterable

from live.operations import Operation, get, registry
from ninja import Schema

from base import assistant
from base.tests.test_assistant import named_actions, named_operations, verb


class NothingIn(Schema):
    pass


def action(op: Operation) -> str:
    return assistant.cards.card(op, {}, "en")["action"]


def writes() -> list[Operation]:
    return [op for op in registry.values() if op.kind == "command" and assistant.tools.is_tool(op)]


def said_alone(operations: Iterable[Operation], verbs: dict[str, dict[str, str]]) -> list[str]:
    """The writes the assistant may call that take no data and say their action's verb, which another write the
    assistant may call says too (``verbs``: ``named_operations``): their card would not say which of them it is."""
    every = writes()
    return sorted(
        f"{language}: {op.name}"
        for op in operations
        if op.kind == "command" and assistant.tools.is_tool(op) and not op.input.model_fields
        for language, named in verbs.items()
        if op.name not in named
        and any(other.name != op.name and other.name not in named and action(other) == action(op) for other in every)
    )


def test_a_break_and_every_write_that_takes_no_data_say_what_they_do():
    verbs = named_actions()
    said = {
        "attendance.break.start": ("Empezar la pausa", "Start a break"),
        "attendance.break.end": ("Terminar la pausa", "End the break"),
        "attendance.record.review_stale": ("Marcar para revisar los días olvidados", "Flag forgotten days for review"),
        "base.device.prune": ("Quitar los dispositivos sin usar", "Remove the unused devices"),
        "base.failed_event.retry_all": ("Reintentar todos los eventos caídos", "Retry all failed events"),
        "base.profile.avatar_remove": ("Quitar la foto del perfil", "Remove the profile photo"),
        "cart_checkout.cart.cleanup_expired": ("Limpiar los carritos caducados", "Clean up the expired carts"),
        "cash_register.session.auto_close": (
            "Cerrar las sesiones que debían cerrarse solas",
            "Close the sessions due to close by themselves",
        ),
        "reservation.reservation.release_unconfirmed": (
            "Liberar las reservas sin confirmar",
            "Release the unconfirmed reservations",
        ),
        "schedule.week.confirm": ("Confirmar el horario de la semana", "Confirm the weekly hours"),
        "verifactu.certificate.remove": ("Quitar el certificado", "Remove the certificate"),
        "verifactu.contingency.process": ("Procesar la cola ahora", "Process the queue now"),
        "whatsapp_inbox.channel.prepare": ("Preparar la conexión", "Prepare the connection"),
    }
    assert {name: (verb(get(name), verbs["es"], "es"), verb(get(name), verbs["en"])) for name in said} == said


def test_no_write_that_takes_no_data_says_a_verb_another_write_says_too():
    assert said_alone(registry.values(), named_operations()) == []


def test_the_guardrail_catches_a_write_with_no_data_that_says_a_shared_verb():
    """A write with no data whose action is «remove», the verb of taking a line out of a cart: listed until it has a
    verb of its own."""
    bare = Operation(
        name="demo.item.remove",
        kind="command",
        permission="demo.manage",
        input=NothingIn,
        output=NothingIn,
        expose_api=False,
        ai={"description": "Removes something nobody says."},
        fn=lambda ctx, data: data,
    )
    assert said_alone([bare], {"en": {}, "es": {}}) == ["en: demo.item.remove", "es: demo.item.remove"]
    assert said_alone([bare], {"en": {"demo.item.remove": "Remove it"}, "es": {"demo.item.remove": "Quitarlo"}}) == []
    # A write that takes data names what it acts on in its line: it may say a shared verb.
    assert said_alone([get("cart_checkout.item.remove")], {"en": {}, "es": {}}) == []
