"""A key the person dictates to the assistant never goes into a call as it is (FLOW-F26, FLOW-F27).

Written out in a header, it would be on view to whoever opens the automation. When the assistant asks for it, the Hub
refuses it before any card: the model hears why and tells the person to save the key in «Secrets» and to name it,
``{{secret.NAME}}``. On the screen or by the API a person may still type a header by hand, as in Zapier, Make or n8n.
"""

import dataclasses

import pytest
from cryptography.fernet import Fernet
from live.errors import InvalidPayload

from apps.flow import vault
from apps.flow.models import Flow, Secret
from apps.invoice.tests.conftest import catalog_of
from base.models import Membership
from base.tests.test_assistant_asks import assert_offered_or_found
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, the_model_hears
from base.tests.test_services_assistant import asked, call

from .conftest import HUB_DB, TASK_STEP, ctx_for, make_flow, run

__all__ = ["catalog_of"]

pytestmark = HUB_DB

#: The owner's words in the QA, as said to the assistant.
DICTATED = (
    "A la de revisar ventas grandes añádele otro aviso a https://example.com/qa-otro-aviso por POST, y en la cabecera "
    "de acceso le pones la clave QA-PRUEBA-5678."
)
KEY_IN_STEP = "flow.key_in_step"


@pytest.fixture(autouse=True)
def key(settings):
    settings.FLOW_SECRETS_KEY = Fernet.generate_key().decode()


def _call(**headers) -> dict:
    return {"id": "s2", "kind": "http", "method": "POST", "url": "https://example.com/qa-otro-aviso", "headers": headers}


def _sent(write: str, header: dict) -> dict:
    steps = [TASK_STEP, _call(**header)]
    return {"flow": "revisar ventas grandes", "steps": steps} if write == "flow.flow.update" else {"steps": steps}


def _turn(arguments: dict, write: str) -> dict:
    """The turn after the model asked for ``write`` with ``arguments``, the owner having said ``DICTATED``."""
    owner = dataclasses.replace(ctx_for("hub_owner"), language="es")
    asking = call(write, arguments)
    data = {"messages": [{"role": "user", "content": DICTATED}, asked(asking)], "pending": [asking]}
    return run("base.assistant.turn", data, owner).model_dump(mode="json")


@pytest.fixture
def big_sales():
    return make_flow("Revisar ventas grandes", enabled=False)


def test_the_owners_words_reach_the_change_of_the_automation(catalog_of):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert_offered_or_found(tools, "flow.flow.update", DICTATED, "cambiar una automatización")


@pytest.mark.parametrize("write", ["flow.flow.update", "flow.flow.create"])
def test_a_key_dictated_to_the_assistant_draws_no_card_and_the_model_hears_to_save_it_as_a_secret(big_sales, write):
    plan = _turn(_sent(write, {"Authorization": "QA-PRUEBA-5678"}), write)
    no_card_but_the_model_hears(plan, KEY_IN_STEP)
    assert list(the_model_hears(plan)["fields"]) == ["steps.1.headers"]
    big_sales.refresh_from_db()
    assert big_sales.steps == [TASK_STEP] and Flow.objects.count() == 1


@pytest.mark.parametrize("write", ["flow.flow.update", "flow.flow.create"])
def test_a_key_named_by_its_secret_draws_the_card(big_sales, write):
    Secret.objects.create(name="AVISO_KEY", ciphertext=vault.seal("QA-PRUEBA-5678"))
    plan = _turn(_sent(write, {"Authorization": "Bearer {{secret.AVISO_KEY}}"}), write)
    assert plan["confirm"]["operation"] == write, plan["append"]


def test_a_key_typed_on_the_screen_is_kept_as_typed(big_sales):
    run("flow.flow.update", _sent("flow.flow.update", {"Authorization": "QA-PRUEBA-5678"}), ctx_for("hub_owner"))
    big_sales.refresh_from_db()
    assert big_sales.steps[1]["headers"] == {"Authorization": "QA-PRUEBA-5678"}


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("Authorization", "QA-PRUEBA-5678"),
        ("Authorization", "Bearer QA-PRUEBA-5678"),
        ("authorization", "Bearer QA-PRUEBA-5678"),
        ("Proxy-Authorization", "Basic dXNlcjpwYXNz"),
        ("X-API-Key", "QA-PRUEBA-5678"),
        ("apikey", "QA-PRUEBA-5678"),
        ("X-Auth-Token", "QA-PRUEBA-5678"),
        ("X-Access-Token", "QA-PRUEBA-5678"),
        ("Authorization", "Bearer {{secret.AVISO_KEY}} QA-PRUEBA-5678"),
    ],
)
def test_a_credential_header_written_out_is_refused(name, value):
    with pytest.raises(InvalidPayload) as refused:
        run("flow.flow.check", {"steps": [_call(**{name: value})]})
    assert refused.value.code == KEY_IN_STEP
    assert list(refused.value.fields) == ["steps.0.headers"]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("Authorization", "Bearer {{secret.AVISO_KEY}}"),
        ("Authorization", "{{secret.AVISO_KEY}}"),
        ("X-API-Key", "{{ secret.AVISO_KEY }}"),
        ("X-Auth-Token", "{{steps.s1.id}}"),
        ("Idempotency-Key", "{{run.idempotency_key}}"),
        ("Content-Type", "application/json"),
        ("Authorization", ""),
    ],
)
def test_a_header_that_names_its_key_or_carries_none_is_taken(name, value):
    Secret.objects.create(name="AVISO_KEY", ciphertext=vault.seal("QA-PRUEBA-5678"))
    assert run("flow.flow.check", {"steps": [TASK_STEP, _call(**{name: value})]}).calls == 1


def test_a_change_that_sends_no_steps_has_nothing_to_check():
    assert run("flow.flow.check", {}).calls == 0
