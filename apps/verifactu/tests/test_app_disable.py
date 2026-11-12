"""VeriFactu never goes off once on, in Spain (VERIFACTU-F32).

The platform's ``base.app.disable`` asks the app's ``can_disable`` (``base.activation.veto``). A business in Spain that
turned VeriFactu on has its invoices reach the AEAT from then on: VERI*FACTU binds it at least to the end of the
natural year (RD 1007/2023, Orden HAC/1177/2024) and ERPlora keeps no other way of recording them, so the answer is
always 409 ``base.app_vetoed`` with the legal reason in the reader's language, and the app stays on — whether records
are still to send or the AEAT answered all of them. A business without a country (a demo) is in Spain. Outside Spain
nothing is ever sent (``test_outside_spain``), so it goes off. So does one that never got on: its tables still being
made, or making them failed (S3, ``base.activation``), it sealed nothing and the rule does not bind it yet. Each hub
reads its own business's country: a business outside Spain in hub A turns it off while the one in Spain in hub B is
refused.
"""

import pytest
from django.apps import apps
from live.context import OperationContext, Scope
from live.errors import Conflict
from live.operations import get

from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import A, business_in, ctx_for, run
from base import activation
from base.models import AppActivation
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
@pytest.mark.parametrize("state", [activation.CREATING, activation.FAILED])
def test_a_verifactu_that_never_got_on_goes_off(state):
    business_in("ES")
    AppActivation.objects.update_or_create(host="a", app="verifactu", defaults={"state": state, "chosen": True})

    assert apps.get_app_config("verifactu").can_disable(admin()) is None
    assert disable()["state"] == "off"
    assert activation.states_of(A)["verifactu"].state == activation.OFF


@pytest.mark.django_db
def test_the_reason_is_in_the_language_of_whoever_turns_it_off():
    assert refusal(admin(language="es")).message == NEVER_OFF_ES


#: What VeriFactu needs that only it keeps on. Taxes, which it needs too, never goes off anyway: it is mandatory in every
#: country and says so itself (hub#997, ``test_taxes_says_it_is_mandatory_before_that_verifactu_needs_it``).
NAMES = {"invoice": "Invoicing", "sale": "Sales & POS", "customer": "Customers"}
NAMES_ES = {"invoice": "Facturación", "sale": "Ventas / TPV", "customer": "Clientes"}


@pytest.mark.django_db
@pytest.mark.parametrize("app", list(NAMES))
def test_what_verifactu_needs_stays_on_with_it_and_says_why(app):
    """hub#619: never «Turn off VeriFactu first», which nobody can do: the real reason, VeriFactu's."""
    business_in("ES")

    refused = refusal(app=app)

    error = refused.envelope()["error"]
    assert (refused.status, error["code"], error["app"]) == (409, "base.app_vetoed", "verifactu")
    assert refused.message == f"{NAMES[app]} can't be turned off: VeriFactu needs it. {NEVER_OFF}"
    assert is_on(app=app)
    assert is_on()


@pytest.mark.django_db
@pytest.mark.parametrize("app", list(NAMES))
def test_that_reason_is_in_the_language_of_whoever_turns_it_off(app):
    business_in("ES")

    refused = refusal(admin(language="es"), app=app)

    assert refused.message == f"{NAMES_ES[app]} no se puede desactivar: hace falta para VeriFactu. {NEVER_OFF_ES}"


@pytest.mark.django_db
@pytest.mark.parametrize("app", list(NAMES))
def test_outside_spain_turning_verifactu_off_first_is_what_there_is_to_do(app):
    business_in("PL")

    refused = refusal(app=app)

    error = refused.envelope()["error"]
    assert (refused.status, error["code"]) == (409, "base.app_required")
    assert "verifactu" in error["required_by"]
    assert "VeriFactu" in refused.message


@pytest.mark.django_db
@pytest.mark.parametrize(("country", "named"), [("ES", "Spain"), ("", "Spain"), ("PL", "Poland")])
def test_taxes_says_it_is_mandatory_before_that_verifactu_needs_it(country, named):
    """hub#997: Taxes, mandatory in every country, gives base's reason, its own, in Spain with VeriFactu on too:
    turning VeriFactu off would still leave it on. Apps says the same beforehand."""
    business_in(country)
    reason = f"Taxes is mandatory for businesses in {named}: it can't be turned off."

    refused = refusal(app="tax")

    error = refused.envelope()["error"]
    assert (refused.status, error["code"], error["app"], refused.message) == (409, "base.app_vetoed", "tax", reason)
    assert is_on(app="tax")
    assert rows_of_the_list()["tax"]["refusal"] == reason


# ── What Apps says beforehand (hub#618): it never offers what is always refused ─────────────────────────────────────


def rows_of_the_list(language: str = "en") -> dict[str, dict]:
    op = get("base.app.list")
    document = op(admin(language=language), op.input()).model_dump(mode="json")
    return {row["id"]: row for row in document["apps"]}


@pytest.mark.django_db
@pytest.mark.parametrize("country", ["ES", ""])
def test_in_spain_the_list_says_verifactu_and_what_it_needs_stay_on(country):
    business_in(country)

    rows = rows_of_the_list()

    assert rows["verifactu"]["refusal"] == NEVER_OFF
    for app, name in NAMES.items():
        assert rows[app]["refusal"] == f"{name} can't be turned off: VeriFactu needs it. {NEVER_OFF}"
    assert rows["task"]["refusal"] is None


@pytest.mark.django_db
def test_the_list_says_it_in_the_language_of_who_reads():
    business_in("ES")

    assert rows_of_the_list("es")["verifactu"]["refusal"] == NEVER_OFF_ES


@pytest.mark.django_db
def test_outside_spain_the_list_refuses_nothing_of_a_verifactu_that_is_on():
    business_in("PL")

    rows = rows_of_the_list()

    assert rows["verifactu"]["state"] == "on"
    assert {app: rows[app]["refusal"] for app in ("verifactu", *NAMES)} == dict.fromkeys(("verifactu", *NAMES))


@pytest.mark.django_db
@pytest.mark.parametrize("state", [activation.CREATING, activation.FAILED])
def test_the_list_lets_go_a_verifactu_that_never_got_on(state):
    business_in("ES")
    AppActivation.objects.update_or_create(host="a", app="verifactu", defaults={"state": state, "chosen": True})

    assert rows_of_the_list()["verifactu"]["refusal"] is None


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_each_hub_reads_its_own_business_country(hub_a, hub_b, poland_and_spain):
    of_a, of_b = poland_and_spain

    with context.use_hub(hub_a):
        assert disable(admin(of_a))["state"] == "off"
        assert not is_on(of_a)
    with context.use_hub(hub_b):
        assert refusal(admin(of_b)).message == NEVER_OFF
        assert is_on(of_b)


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_each_hub_lists_what_its_own_business_country_refuses(hub_a, hub_b, poland_and_spain):
    of_a, of_b = poland_and_spain
    op = get("base.app.list")

    def refusal_in(scope: Scope) -> str | None:
        document = op(admin(scope), op.input()).model_dump(mode="json")
        return {row["id"]: row for row in document["apps"]}["verifactu"]["refusal"]

    with context.use_hub(hub_a):
        assert is_on(of_a)
        assert refusal_in(of_a) is None
    with context.use_hub(hub_b):
        assert is_on(of_b)
        assert refusal_in(of_b) == NEVER_OFF
