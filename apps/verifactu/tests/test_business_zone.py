"""VeriFactu reads the hours of a business in another zone on the business's clock, not the deployment's (Madrid): the
time a record is generated at, the hour the AEAT asks it to wait until, the month it asks the AEAT about and the day a
certificate expires. Records are sealed in the AEAT's testing environment and the gateway's transport is replaced:
nothing here leaves the machine."""

import datetime as dt
import re

import pytest
from django.utils import timezone
from live.errors import Conflict

from apps.verifactu import certificates
from apps.verifactu.models import Event, Record, SendControl
from apps.verifactu.tests.conftest import HUB_DB, aeat_holds, b64, make_p12, run, ticket

pytestmark = [HUB_DB, pytest.mark.usefixtures("nothing_leaves")]

#: 23:30 of 2 November in the Canary Islands; 00:30 of the 3rd in Madrid.
CANARY_NIGHT = ("Atlantic/Canary", dt.datetime(2026, 11, 2, 23, 30, tzinfo=dt.UTC))
#: 23:30 of 31 December 2026 in the Canary Islands; 00:30 of 1 January 2027 in Madrid.
CANARY_NEW_YEARS_EVE = ("Atlantic/Canary", dt.datetime(2026, 12, 31, 23, 30, tzinfo=dt.UTC))
#: A certificate that expires at 21:00 of 2 November in Bogotá, 03:00 of the 3rd in Madrid.
BOGOTA_EXPIRY = dt.datetime(2026, 11, 3, 2, 0, tzinfo=dt.UTC)
ERPLORA_NIF = "B27593136"


@pytest.fixture
def at(monkeypatch, in_business_a):
    """``at((zone, instant))``: business A in ``zone``, its clock stopped at ``instant``."""

    def move(moment):
        zone, instant = moment
        monkeypatch.setattr(timezone, "now", lambda: instant)
        monkeypatch.setattr(in_business_a, "timezone", zone)

    return move


@pytest.fixture
def held_back(at, issuer):
    """A ticket sealed at 23:30 of the Canary Islands, and the AEAT asking its chain to wait one minute more."""
    at(CANARY_NIGHT)
    record = Record.objects.get(invoice_id=ticket().id)
    SendControl.objects.update_or_create(
        issuer_nif=record.issuer_nif,
        environment=record.environment,
        defaults={"next_send_at": CANARY_NIGHT[1] + dt.timedelta(minutes=1)},
    )
    return record


@pytest.fixture
def storage(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()


def asked_period(gateway_answers) -> tuple[str, str]:
    """The year and month of the query the gateway was handed."""
    envelope = gateway_answers.calls[0][1]["envelope"]
    return tuple(re.search(rf"<(?:\w+:)?{tag}>([^<]*)</", envelope).group(1) for tag in ("Ejercicio", "Periodo"))


def test_a_record_is_generated_at_the_business_s_hour_and_its_chain_still_checks_out(at, issuer):
    at(CANARY_NIGHT)
    record = Record.objects.get(invoice_id=ticket().id)
    assert (record.issue_date, record.generated_at) == (dt.date(2026, 11, 2), "2026-11-02T23:30:00+00:00")
    assert run("verifactu.chain.validate").valid is True


def test_a_record_held_back_by_the_aeat_says_until_when_on_the_business_s_clock(held_back, settings):
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    detail = run("verifactu.record.get", {"record_id": str(held_back.id)})
    (reason,) = [reason for reason in detail.waiting if reason.code == "aeat_wait"]
    assert "23:31:00" in reason.message
    assert "00:31:00" not in reason.message


def test_sending_now_what_the_aeat_holds_back_says_when_on_the_business_s_clock(held_back, gateway_answers):
    with pytest.raises(Conflict) as refused:
        run("verifactu.record.transmit", {"record_id": str(held_back.id)})
    assert refused.value.code == "verifactu.aeat_wait"
    assert "23:31:00" in str(refused.value)
    assert gateway_answers.calls == []


def test_on_new_year_s_eve_the_aeat_is_asked_about_the_business_s_month(at, issuer, gateway_answers):
    at(CANARY_NEW_YEARS_EVE)
    gateway_answers.set(aeat_holds())
    run("verifactu.aeat.query", {"issuer_nif": ERPLORA_NIF})
    assert asked_period(gateway_answers) == ("2026", "12")


def test_on_new_year_s_eve_a_chain_is_recovered_from_the_business_s_month(at, issuer, gateway_answers):
    at(CANARY_NEW_YEARS_EVE)
    gateway_answers.set(aeat_holds())
    run("verifactu.chain.recover_from_aeat", {"issuer_nif": ERPLORA_NIF})
    assert asked_period(gateway_answers) == ("2026", "12")


def test_an_expired_certificate_says_the_day_it_expired_on_the_business_s_clock(at, issuer, storage):
    at(("America/Bogota", dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.UTC)))
    p12 = make_p12(expires_at=BOGOTA_EXPIRY)
    with pytest.raises(Conflict) as refused:
        run("verifactu.certificate.upload", {"p12_base64": b64(p12), "password": "secret"})
    assert refused.value.code == "verifactu.certificate_invalid"
    assert "2026-11-02" in str(refused.value)


def test_an_uploaded_certificate_is_noted_with_its_expiry_day_on_the_business_s_clock(at, issuer, storage):
    at(("America/Bogota", dt.datetime(2025, 11, 10, 12, 0, tzinfo=dt.UTC)))
    p12 = make_p12(expires_at=BOGOTA_EXPIRY)
    run("verifactu.certificate.upload", {"p12_base64": b64(p12), "password": "secret"})
    run("verifactu.certificate.remove")
    noted = Event.objects.filter(message_key__in=("certificate_uploaded", "certificate_removed"))
    assert sorted(event.params["expires_on"] for event in noted) == ["2026-11-02", "2026-11-02"]
