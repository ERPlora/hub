"""What the assistant is told about the checklist «Finish setting up your business» (``base.setup.status``).

Asked about the step «Your catalog» of a business with seventeen products, the model answered «It only needs at least
one product in the catalog, and you have one.»: the step came done with its line on the list, «Add at least one product
so there is something to sell.», and the model read what the step asks for as what the business has. The read tells it
that a step's texts never say what the business has, and where to read it.
"""

from live.assistant import description
from live.operations import get

from base.assistant.prompt import setup_block


def setup_read() -> str:
    return description(get("base.setup.status"))


def test_a_step_text_is_what_it_asks_for_never_what_the_business_has():
    said = setup_read()
    assert "A step's title and description are its line on the list, what the step asks for, " in said
    assert "what the step asks for, never what the business has now" in said


def test_a_done_step_that_asks_for_at_least_one_is_done_because_there_are_some():
    said = setup_read()
    assert "done only says it is met" in said
    assert "a step asking for at least one of something is done because there are some, not because there is one" in said


def test_a_count_or_a_setting_comes_from_a_tool_of_the_step_app():
    said = setup_read().partition("never give a count, a name or a setting from those texts")[2]
    assert said.startswith("; read it with a tool of the step's app.")


def test_the_read_tells_the_model_to_name_the_list_by_the_title_it_answers():
    assert "`title`" in setup_read()


def test_in_setup_the_instructions_name_the_list_by_its_title_in_the_language_of_who_asks():
    """The checklist read again in setup carries its title as the Home shows it to this person (``base.setup.status``):
    the instructions name the list by it, never by the English words of the screen."""
    step = {"state": "pending", "title": "Tu equipo", "description": "Añade a las personas.", "level": "recommended",
            "actionable": True, "route": "/employees"}
    status = {"title": "Termina de configurar tu negocio", "total": 1, "pending": 1, "unavailable": 0, "items": [step]}
    said = setup_block(status)
    assert "«Termina de configurar tu negocio»" in said
    assert "Finish setting up" not in said
