"""A question to the Hub's assistant that carries a file is offered the tools its words ask for: the turn ranks the
text of a message that brings files as it ranks a message of text alone."""

import pytest
from live.context import OperationContext
from live.operations import get

from base.models import Membership
from base.permissions import permissions_for
from base.tenancy.tests.business import HUB_DB, A, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB

SHEET = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILE ={"type": "input_file", "filename": "carta.xlsx", "mime_type": SHEET, "data": "UEsDBBQAAAAIAA=="}
WORDS = "da de alta estos productos de la carta"


@pytest.fixture
def owner(make_user):
    user = make_user("olga", host=A.key, role=Membership.Role.OWNER)
    return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language="es")


def offered(ctx: OperationContext, *messages: dict) -> list[str]:
    op = get("base.assistant.turn")
    plan = op(ctx, op.input(messages=list(messages))).model_dump(mode="json")
    return [tool["name"] for tool in plan["tools"]]


def test_a_question_with_a_file_attached_is_offered_the_tools_its_words_ask_for(owner):
    plain = offered(owner, {"role": "user", "content": WORDS})
    with_file = offered(owner, {"role": "user", "content": [{"type": "text", "text": WORDS}, FILE]})

    assert "inventory__product__bulk_create" in plain
    assert with_file == plain


def test_a_file_sent_alone_keeps_the_tools_of_what_was_asked_before_it(owner):
    tools = offered(
        owner,
        {"role": "user", "content": WORDS},
        {"role": "assistant", "content": "Pásame la carta."},
        {"role": "user", "content": "Vale, ahora te la paso."},
        {"role": "assistant", "content": "Cuando quieras."},
        {"role": "user", "content": [FILE]},
    )

    assert "inventory__product__bulk_create" in tools
