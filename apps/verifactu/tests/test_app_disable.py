"""VeriFactu refuses to go off while its queue holds records (VERIFACTU-F32, FIX-BASE-APP-TURN-OFF-VETO).

The platform's ``base.app.disable`` asks the app's ``can_disable`` (``base.activation.veto``): while a record is not in
the AEAT yet (``Record.UNSENT``: pending, a retry waiting included, or sent without an answer) the answer is 409
``base.app_vetoed`` with the reason and how many, in the reader's language, and the app stays on. What the AEAT
answered (accepted, with errors or rejected, which only a new record corrects) leaves the queue: then it goes off.
A record still to send in hub B never vetoes in A.
"""

import datetime as dt

import pytest
from django.apps import apps
from django.utils import timezone
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.operations import get

from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import A, ISSUER, ctx_for, run
from base import activation
from base.tenancy import context
from base.tenancy.tests import hubs

TWO_TO_SEND = (
    "VeriFactu still has 2 records to send to the AEAT. Wait until they are sent or fix them before turning it off."
)
ONE_TO_SEND = (
    "VeriFactu still has 1 record to send to the AEAT. Wait until it is sent or fix it before turning it off."
)


def admin(scope: Scope = A, language: str = "en") -> OperationContext:
    """Whoever administers the business (``base.administer_hub``), in ``language``."""
    return OperationContext(scope=scope, actor="ana", permissions=frozenset({"*"}), language=language)


def disable(context_: OperationContext | None = None) -> dict:
    op = get("base.app.disable")
    return op(context_ or admin(), op.input.model_validate({"app": "verifactu"})).model_dump(mode="json")


def ticket(scope: Scope = A) -> Record:
    """A ticket issued through Invoicing's own operation, with the record VeriFactu seals for it (``pending``)."""
    invoice = run(
        "invoice.invoice.create",
        {
            "series_code": "TICKET",
            "lines": [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}],
        },
        ctx_for(scope=scope),
    )
    return Record.objects.get(invoice_id=invoice.id)


def refusal(context_: OperationContext | None = None) -> Conflict:
    with pytest.raises(Conflict) as refused:
        disable(context_)
    return refused.value


def is_on(scope: Scope = A) -> bool:
    return activation.states_of(scope)["verifactu"].on


@pytest.fixture
def no_test_fallback(monkeypatch):
    """As production: without ``use_hub`` a hub's model fails, nothing falls back on the shared database."""
    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.mark.django_db
def test_records_still_to_send_keep_verifactu_on_and_say_how_many(issuer):
    waiting, retrying = ticket(), ticket()
    Record.objects.filter(pk=retrying.pk).update(
        attempts=3, next_attempt_at=timezone.now() + dt.timedelta(minutes=20), wait_reason="unknown"
    )

    refused = refusal()

    error = refused.envelope()["error"]
    assert (refused.status, error["code"], error["app"]) == (409, "base.app_vetoed", "verifactu")
    assert refused.message == TWO_TO_SEND
    assert is_on()
    assert Record.objects.get(pk=waiting.pk).status == Record.Status.PENDING


@pytest.mark.django_db
def test_a_record_sent_without_an_answer_is_still_to_send_and_one_is_said_in_singular(issuer):
    Record.objects.filter(pk=ticket().pk).update(status=Record.Status.SENT, attempts=1)

    assert refusal().message == ONE_TO_SEND
    assert is_on()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("count", "said"),
    [
        (1, "VeriFactu aún tiene 1 registro por enviar a la AEAT. Espera a que se envíe o arréglalo antes de desactivarla."),
        (
            2,
            "VeriFactu aún tiene 2 registros por enviar a la AEAT. Espera a que se envíen o arréglalos antes de "
            "desactivarla.",
        ),
    ],
)
def test_the_reason_is_in_the_language_of_whoever_turns_it_off(issuer, count, said):
    for _ in range(count):
        ticket()

    assert refusal(admin(language="es")).message == said


@pytest.mark.django_db
def test_once_the_aeat_answered_every_record_it_goes_off(issuer):
    for record, status in zip(
        (ticket(), ticket(), ticket()),
        (Record.Status.ACCEPTED, Record.Status.ACCEPTED_WITH_ERRORS, Record.Status.REJECTED),
        strict=True,
    ):
        Record.objects.filter(pk=record.pk).update(status=status)

    assert apps.get_app_config("verifactu").can_disable(admin()) is None
    assert disable()["state"] == "off"
    assert not is_on()


@pytest.mark.django_db
def test_without_any_record_it_goes_off():
    assert disable()["state"] == "off"
    assert not is_on()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_a_record_still_to_send_in_hub_b_never_vetoes_in_a(hub_a, hub_b, no_test_fallback):
    of_a, of_b = Scope("host", hub_a.slug), Scope("host", hub_b.slug)
    with context.use_hub(hub_b):
        run("invoice.issuer.update", ISSUER, ctx_for(scope=of_b))
        ticket(of_b)

    with context.use_hub(hub_a):
        assert disable(admin(of_a))["state"] == "off"
    with context.use_hub(hub_b):
        assert refusal(admin(of_b)).message == ONE_TO_SEND
        assert is_on(of_b)
