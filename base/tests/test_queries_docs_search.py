"""``base.docs.search`` (saas ASSISTANT-F28): the Hub's assistant answers how-to questions from ERPlora's own
documentation, never from memory. The Hub keeps no index: it asks erplora.com's one index (the public help, the user
part of every app's WORKBOOK, the panel's manuals and the plans) through ``POST /internal/assistant/docs/search``,
signed as every ``/internal`` call, naming this business, the person's question and the language they read.

A tool of everybody who opens the Hub (``base.view_home``), always offered (``assistant.ALWAYS``): a how-to question
shares no word with the tool. What erplora.com cannot answer is a 503 ``base.assistant_unavailable`` the model relays,
never excerpts made up. It waits on the network, so it holds no transaction (``database=False``); inside a turn the
route asks before the turn's transaction opens (``assistant.prepare``). erplora.com is ``fake_gateway``.
"""

import pytest
from django.db import connections
from live.assistant import is_tool
from live.context import OperationContext, Scope
from live.errors import OperationError
from live.operations import AI, get
from pydantic import ValidationError

from base import assistant
from base.schemas import AssistantCallIn
from base.tests.fake_gateway import gateway, signed  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

A = Scope("host", "a")
DOCS = "/internal/assistant/docs/search"
EXCERPT = {
    "source": "app_doc",
    "path": "app_doc:cash_register",
    "heading": "Caja > Abrir la caja",
    "text": "Abre la caja desde Caja > Abrir con el efectivo inicial.",
    "score": 0.91,
    "lang": "es",
}


def ctx(language="es", permissions=frozenset({"base.view_home"}), actor="ana"):
    return OperationContext(scope=A, actor=actor, permissions=frozenset(permissions), language=language)


def calls(*pending: dict) -> list[AssistantCallIn]:
    return [AssistantCallIn(call_id=f"c{index}", **call) for index, call in enumerate(pending)]


HOW_TO = {"name": "base__docs__search", "arguments": '{"query": "¿Cómo abro la caja?"}'}


def search(language="es", **data):
    op = get("base.docs.search")
    return op(ctx(language), op.input.model_validate({"query": "¿Cómo abro la caja?", **data})).model_dump(mode="json")


class TestTheOperation:
    def test_it_is_a_read_of_everybody_that_holds_no_transaction_and_is_a_tool(self):
        op = get("base.docs.search")
        assert (op.kind, op.permission, op.database) == ("query", "base.view_home", False)
        assert isinstance(op.ai, AI) and is_tool(op)
        assert "how-to" in op.ai.description and "Not for the business's own records" in op.ai.description

    def test_it_asks_erplora_com_signed_for_this_business_in_the_persons_language(self, gateway):
        gateway.reply(DOCS, json={"results": [EXCERPT]})

        found = search()

        assert found == {"results": [EXCERPT]}
        [seen] = gateway.sent(DOCS)
        assert seen.body == {"hub": "a", "query": "¿Cómo abro la caja?", "language": "es", "limit": 8}
        assert signed(seen)

    @pytest.mark.parametrize(("language", "asked"), [("en", "en"), ("es", "es"), ("es-ES", "es"), ("fr", "en")])
    def test_the_documentation_is_read_in_spanish_or_else_in_english(self, gateway, language, asked):
        gateway.reply(DOCS, json={"results": []})

        search(language)

        assert gateway.sent(DOCS)[0].body["language"] == asked

    def test_at_most_twelve_excerpts_are_asked_for(self, gateway):
        gateway.reply(DOCS, json={"results": []})
        gateway.reply(DOCS, json={"results": []})

        search(limit=50)
        search(limit=3)

        assert [seen.body["limit"] for seen in gateway.sent(DOCS)] == [12, 3]

    @pytest.mark.parametrize("data", [{"query": ""}, {"query": "   "}, {"query": "x" * 501}, {"limit": 0}])
    def test_a_question_out_of_the_contract_is_refused_before_asking(self, gateway, data):
        with pytest.raises(ValidationError):
            search(**data)
        assert gateway.requests == []

    def test_no_excerpt_is_an_empty_answer(self, gateway):
        gateway.reply(DOCS, json={"results": []})

        assert search() == {"results": []}

    @pytest.mark.parametrize(
        "reply",
        [
            {"status": 409, "json": {"error": {"code": "assistant.provider_not_configured", "message": "x"}}},
            {"status": 503, "json": {"error": {"code": "assistant.provider_unavailable", "message": "x"}}},
            {"status": 429, "json": {"error": {"code": "rate_limited", "message": "x"}}},
            {"status": 404, "json": {"error": {"code": "hub_unknown", "message": "x"}}},
        ],
    )
    def test_what_erplora_com_cannot_answer_is_said_never_made_up(self, gateway, reply):
        gateway.reply(DOCS, **reply)

        with pytest.raises(OperationError) as caught:
            search()

        assert (caught.value.status, caught.value.code) == (503, "base.assistant_unavailable")

    @pytest.mark.parametrize("answer", [{}, {"results": "none"}, {"results": [{"text": "no source"}]}])
    def test_an_answer_that_is_not_the_doors_contract_is_refused_not_passed_on(self, gateway, answer):
        gateway.reply(DOCS, json=answer)

        with pytest.raises(OperationError) as caught:
            search()

        assert (caught.value.status, caught.value.code) == (503, "base.assistant_unavailable")

    def test_a_gateway_that_does_not_answer_is_the_same_refusal_in_the_persons_language(self, settings):
        settings.SAAS_INTERNAL_URL = "http://127.0.0.1:9"

        with pytest.raises(OperationError) as english:
            search("en")
        with pytest.raises(OperationError) as spanish:
            search("es")

        assert english.value.code == spanish.value.code == "base.assistant_unavailable"
        assert str(english.value.message).startswith("ERPlora's documentation could not be searched now")
        assert str(spanish.value.message) != str(english.value.message)


class TestPreparedBeforeTheTurn:
    """Inside a turn (``base.assistant.turn``, a transaction) the search reads what its route asked before."""

    def test_a_prepared_search_is_not_asked_again(self, gateway):
        gateway.reply(DOCS, json={"results": [EXCERPT]})
        pending = calls(HOW_TO)

        with assistant.prepared_docs(assistant.prepare_docs(ctx(), pending)):
            found = search()

        assert found == {"results": [EXCERPT]}
        assert len(gateway.sent(DOCS)) == 1

    def test_a_search_that_failed_while_prepared_is_refused_without_asking_again(self, gateway):
        gateway.reply(DOCS, status=503, json={"error": {"code": "assistant.provider_unavailable", "message": "x"}})
        pending = calls(HOW_TO)

        with assistant.prepared_docs(assistant.prepare_docs(ctx(), pending)), pytest.raises(OperationError) as caught:
            search()

        assert caught.value.code == "base.assistant_unavailable"
        assert len(gateway.sent(DOCS)) == 1

    @pytest.mark.parametrize(
        "pending",
        [
            calls({"name": "demo__item__list", "arguments": "{}"}),
            calls({"name": "base__docs__search", "arguments": "{not json"}),
            calls({"name": "base__docs__search", "arguments": "[]"}),
            calls({"name": "base__docs__search", "arguments": '{"query": ""}'}),
        ],
    )
    def test_only_the_documentation_searches_the_model_asked_for_are_prepared(self, gateway, pending):
        assert assistant.prepare_docs(ctx(), pending) == {}
        assert gateway.requests == []

    @pytest.mark.parametrize(("actor", "permissions"), [(None, {"base.view_home"}), ("ana", set())])
    def test_nobody_who_may_not_search_makes_erplora_com_search(self, gateway, actor, permissions):
        pending = calls(HOW_TO)

        assert assistant.prepare_docs(ctx(actor=actor, permissions=permissions), pending) == {}
        assert gateway.requests == []


@pytest.mark.django_db(transaction=True)
def test_waiting_for_the_documentation_holds_no_transaction(gateway, monkeypatch):
    """Up to 15 s of waiting inside a transaction would hold the hub's connection (PLAN §14.2), as for every door of
    the gateway (``test_services_assistant.test_waiting_for_erplora_com_holds_no_transaction``)."""
    gateway.reply(DOCS, json={"results": []})
    seen = []
    post = assistant._post

    def probe(*args, **kwargs):
        seen.append(any(connection.in_atomic_block for connection in connections.all()))
        return post(*args, **kwargs)

    monkeypatch.setattr(assistant, "_post", probe)
    search()
    assert seen == [False]
