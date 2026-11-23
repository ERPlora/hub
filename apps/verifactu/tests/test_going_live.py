"""Going live through the assistant (VERIFACTU-F08): while Settings says the business cannot go live yet, the
assistant draws no card for it either.

The owner asked «Switch VeriFactu to the real tax office now» on a server that never files for real and without a
certificate, and the assistant offered the card «Go live in VeriFactu» to type CONFIRM on; the write would only have
refused it after the person's yes (hub#2200). The write is checked before its card with the very refusal it raises
itself, so the model hears why it cannot and tells the person, and the card is still drawn when it can.

Nothing here reaches the AEAT or the gateway: going live only changes the configuration, and the ``offline`` fixture
fails any connection a test would open.
"""

import json

import pytest
from django.utils import translation
from live.context import system_context
from live.errors import Conflict

from apps.verifactu import certificates
from apps.verifactu.models import Config, Environment, OwnCertificate
from apps.verifactu.tests.conftest import (
    HUB_DB,
    A,
    accepted_by_the_aeat_of_testing,
    b64,
    ctx_for,
    make_p12,
    run,
)
from base.tests.test_assistant_yes_for_its_card import turn_as
from base.tests.test_services_assistant import call

pytestmark = [HUB_DB, pytest.mark.usefixtures("offline")]

GO_LIVE = "verifactu.config.go_live"


@pytest.fixture
def opened(settings):
    """The prod deployment opened by ERPlora, with its gateway and the key that keeps the own certificates."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    return settings


@pytest.fixture
def pre(settings):
    """The ``pre`` deployment of the report: it always files in testing, and ERPlora's route is closed to businesses."""
    settings.ERPLORA_ENVIRONMENT = "pre"
    settings.VERIFACTU_PRODUCTION_ENABLED = False
    settings.VERIFACTU_ERPLORA_ROUTE_ENABLED = False
    return settings


def own_certificate(*, accepted: bool) -> None:
    run("verifactu.certificate.upload", {"p12_base64": b64(make_p12()), "password": "secret"})
    if accepted:
        accepted_by_the_aeat_of_testing()


def ask_to_go_live(language: str = "en") -> dict:
    """The owner's turn after the model asked to go live, as the chat's request runs it: in the person's language."""
    with translation.override(language):
        return turn_as(ctx_for("hub_admin", language=language), call(GO_LIVE, {}))


def no_card_but_the_model_hears(plan: dict, code: str) -> dict:
    assert (plan["confirm"], plan["pending"]) == (None, [])
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("error", code)]
    said = json.loads(plan["append"][0]["content"])["error"]
    assert said["code"] == code
    return said


def refusal_of_the_write(language: str) -> Conflict:
    """What the write answers when it is run anyway, as the API and the screen's button run it."""
    with translation.override(language), pytest.raises(Conflict) as refused:
        run(GO_LIVE, ctx=ctx_for("hub_admin", language=language))
    return refused.value


def screen_blockers() -> set[str]:
    """What Settings lists under «It cannot go live yet», by code."""
    return {wait.code for wait in run("verifactu.config.get").live_blockers}


def still_in_testing() -> None:
    assert not Config.objects.filter(environment=Environment.PRODUCTION).exists()


def test_the_reported_turn_draws_no_card_on_a_server_that_never_files_for_real(issuer, pre):
    """hub#2200 as it was seen: ``pre``, testing, no certificate; Settings says it cannot go live."""
    assert "production_closed" in screen_blockers()

    plan = ask_to_go_live()

    no_card_but_the_model_hears(plan, "verifactu.production_closed")
    still_in_testing()


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_model_hears_what_the_write_answers_in_the_persons_language(issuer, pre, language):
    """One path: the assistant hears the refusal the API and the screen's button get, in the person's language."""
    write = refusal_of_the_write(language)

    said = no_card_but_the_model_hears(ask_to_go_live(language), write.code)

    assert said["message"] == str(write)
    assert (said["message"] != str(refusal_of_the_write("en"))) == (language == "es")


def _untested(settings):
    own_certificate(accepted=False)


def _rejected(settings):
    own_certificate(accepted=False)
    OwnCertificate.objects.update(aeat_proof=OwnCertificate.Proof.REJECTED)


def _no_certificate_and_erplora_closed(settings):
    settings.VERIFACTU_ERPLORA_ROUTE_ENABLED = False


def _erplora_without_its_authorisation(settings):
    settings.VERIFACTU_ERPLORA_ROUTE_ENABLED = True


def _account_suspended(settings):
    own_certificate(accepted=True)
    run("verifactu.config.sync", {"version": 1, "hub_status": "suspended"}, system_context(A))


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (_untested, "own_certificate_untested"),
        (_rejected, "own_certificate_rejected"),
        (_no_certificate_and_erplora_closed, "own_certificate_required"),
        (_erplora_without_its_authorisation, "representation_not_approved"),
        (_account_suspended, "hub_not_active"),
    ],
    ids=["certificate untested", "certificate refused", "no certificate", "no authorisation", "account suspended"],
)
def test_an_open_server_draws_no_card_while_settings_says_what_is_missing(issuer, opened, state, code):
    """Every reason Settings gives on a server open for real: the assistant refuses with the one Settings lists."""
    state(opened)
    assert code in screen_blockers()

    no_card_but_the_model_hears(ask_to_go_live(), f"verifactu.{code}")
    still_in_testing()


def test_with_nothing_missing_the_card_is_still_drawn(issuer, opened):
    """Control: an open server, the own certificate the AEAT's test environment accepted, an active account."""
    own_certificate(accepted=True)
    assert screen_blockers() == set()

    plan = ask_to_go_live()

    assert plan["confirm"]["operation"] == GO_LIVE
    assert plan["executed"] == []
    still_in_testing()
