"""What the assistant is told about the checklist «Finish setting up your business» (``base.setup.status``).

Asked about the step «Your catalog» of a business with seventeen products, the model answered «It only needs at least
one product in the catalog, and you have one.»: the step came done with its line on the list, «Add at least one product
so there is something to sell.», and the model read what the step asks for as what the business has. The read tells it
that a step's texts never say what the business has, and where to read it.
"""

from live.assistant import description
from live.operations import get


def setup_read() -> str:
    return description(get("base.setup.status"))


def test_a_step_text_is_what_it_asks_for_never_what_the_business_has():
    assert "what the step asks for, never what the business has now" in setup_read()


def test_a_done_step_that_asks_for_at_least_one_is_done_because_there_are_some():
    assert "done because there are some, not because there is one" in setup_read()


def test_a_count_or_a_setting_comes_from_a_tool_of_the_step_app():
    said = setup_read().partition("never give a count, a name or a setting from those texts")[2]
    assert "read it with a tool of the step's app" in said
