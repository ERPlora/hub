"""Signing out is no tool of the assistant (BASE-F61): the person does it from the user card at the top of the side menu.

Asked «Me voy ya, ciérrame la sesión en esta tableta», the assistant searched its tools, found «Remove this device»
(BASE-F70), whose description said that removing the one in hand signs the person out, and offered to remove the
tablet from the business: whoever used it next had to enter with their erplora.com account again.
"""

import re

import pytest
from live import assistant as shared
from live.context import OperationContext
from live.operations import get, registry

from base.tenancy.tests.business import HUB_DB, A, in_business_a

__all__ = ["in_business_a"]

ADMIN = frozenset({"base.view_home", "base.administer_hub"})
#: Where a person signs out, as BASE-F61 tells it: what the model says to whoever asks it to sign them out.
USER_CARD = "user card at the top of the side menu"
#: A description that says its tool signs someone out: «signs the person out», «logs you out».
SIGNS_SOMEONE_OUT = re.compile(r"\b(?:sign|log)s\b(?:\s+\w+){0,2}\s+out\b", re.IGNORECASE)


def description(op) -> str:
    return " ".join(shared.tool_spec(op)["description"].split())


def test_no_tool_says_it_signs_someone_out():
    tools = (op for _, op in sorted(registry.items()) if shared.is_tool(op))
    assert [op.name for op in tools if SIGNS_SOMEONE_OUT.search(description(op))] == []


@HUB_DB  # the catalogue is of the apps on in the business
@pytest.mark.parametrize(
    ("query", "language"), [("cerrar sesión de este dispositivo", "es"), ("sign out of this device", "en")]
)
def test_searching_how_to_sign_out_here_tells_the_model_where_it_is_done(query, language):
    """The search the model ran in the QA finds «Remove this device», which sends the person to the user card."""
    context = OperationContext(scope=A, actor="ana", permissions=ADMIN, language=language)
    find = get("base.assistant.find_tools")
    found = find(context, find.input(query=query)).model_dump(mode="json")["tools"]
    [remove] = [tool for tool in found if tool["name"] == shared.tool_name("base.device.remove")]
    assert USER_CARD in " ".join(remove["description"].split())
