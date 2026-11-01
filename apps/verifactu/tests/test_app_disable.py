"""VeriFactu never goes off once on, in Spain (VERIFACTU-F32, FIX-HUB-VERIFACTU-NEVER-OFF-ONCE-ON).

The platform's ``base.app.disable`` asks the app's ``can_disable`` (``base.activation.veto``). A business in Spain that
turned VeriFactu on has its invoices reach the AEAT from then on: VERI*FACTU binds it at least to the end of the
natural year (RD 1007/2023, Orden HAC/1177/2024) and ERPlora keeps no other way of recording them, so the answer is
always 409 ``base.app_vetoed`` with the legal reason in the reader's language, and the app stays on — whether records
are still to send or the AEAT answered all of them. A business without a country (a demo) is in Spain. Outside Spain
nothing is ever sent (``test_outside_spain``), so it goes off. Each hub reads its own business's country: a business
outside Spain in hub A turns it off while the one in Spain in hub B is refused.
"""

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.operations import get

from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import A, ctx_for, run
from base import activation
from base.models import Hub
from base.tenancy import context
from base.tenancy.tests import hubs

NEVER_OFF = "VeriFactu can't be turned off once it's on: the law requires your invoices to keep reaching the AEAT."
NEVER_OFF_ES = (
    "VeriFactu no se puede desactivar una vez activada: la ley obliga a que tus facturas sigan llegando a la AEAT."
)


def admin(scope: Scope = A, language: str = "en") -> OperationContext:
    """Whoever administers the business (``base.administer_hub``), in ``language``."""
    return OperationContext(scope=scope, actor="ana", permissions=frozenset({"*"}), language=language)


def disable(context_: OperationContext | None = None, app: str = "verifactu") -> dict:
    op = get("base.app.disable")
    return op(context_ or admin(), op.input.model_validate({"app": app})).model_dump(mode="json")


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


def refusal(context_: OperationContext | None = None, app: str = "verifactu") -> Conflict:
    with pytest.raises(Conflict) as refused:
        disable(context_, app)
    return refused.value


def is_on(scope: Scope = A, app: str = "verifactu") -> bool:
    return activation.states_of(scope)[app].on


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


@pytest.fixture
def no_test_fallback(monkeypatch):
    """As production: without ``use_hub`` a hub's model fails, nothing falls back on the shared database."""
    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.mark.django_db
def test_with_nothing_to_send_verifactu_stays_on_and_says_why():
    business_in("ES")

    refused = refusal()

    error = refused.envelope()["error"]
    assert (refused.status, error["code"], error["app"]) == (409, "base.app_vetoed", "verifactu")
    assert refused.message == NEVER_OFF
    assert is_on()
    assert apps.get_app_config("verifactu").can_disable(admin()) == NEVER_OFF


@pytest.mark.django_db
def test_once_the_aeat_answered_every_record_it_still_stays_on(issuer):
    for record, status in zip(
        (ticket(), ticket(), ticket()),
        (Record.Status.ACCEPTED, Record.Status.ACCEPTED_WITH_ERRORS, Record.Status.REJECTED),
        strict=True,
    ):
        Record.objects.filter(pk=record.pk).update(status=status)

    assert refusal().message == NEVER_OFF
    assert is_on()


@pytest.mark.django_db
def test_records_still_to_send_give_the_same_reason_and_stay_as_they_are(issuer):
    waiting = ticket()

    assert refusal().message == NEVER_OFF
    assert is_on()
    assert Record.objects.get(pk=waiting.pk).status == Record.Status.PENDING


@pytest.mark.django_db
def test_a_business_without_a_country_is_in_spain_and_is_refused_too():
    # A demo has no country: it is in ERPlora's market, Spain.
    business_in("")

    assert refusal().message == NEVER_OFF
    assert is_on()


@pytest.mark.django_db
def test_the_reason_is_in_the_language_of_whoever_turns_it_off():
    assert refusal(admin(language="es")).message == NEVER_OFF_ES


@pytest.mark.django_db
def test_invoicing_stays_on_while_verifactu_needs_it():
    refused = refusal(app="invoice")

    error = refused.envelope()["error"]
    assert (refused.status, error["code"], error["required_by"]) == (409, "base.app_required", ["verifactu"])
    assert is_on(app="invoice")
    assert is_on()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_each_hub_reads_its_own_business_country(hub_a, hub_b, no_test_fallback):
    of_a, of_b = Scope("host", hub_a.slug), Scope("host", hub_b.slug)
    business_in("PL", hub_a.slug)
    business_in("ES", hub_b.slug)

    with context.use_hub(hub_a):
        assert disable(admin(of_a))["state"] == "off"
        assert not is_on(of_a)
    with context.use_hub(hub_b):
        assert refusal(admin(of_b)).message == NEVER_OFF
        assert is_on(of_b)
