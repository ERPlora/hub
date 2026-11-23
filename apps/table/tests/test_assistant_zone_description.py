"""What the assistant is told about a new zone's description, so its card carries only what the person said.

Asked for «another one called Barra QA for people eating at the counter, and it should come first», the model created
the zone with «For people eating at the counter» as its description, which nobody had asked for: the tool only told it
the description was optional. A new zone gets a description only when the person asks to put one on it.
"""

from live.assistant.tools import tool_spec
from live.operations import get


def told() -> str:
    """The text the model reads about the ``description`` datum of ``table.zone.create``."""
    return tool_spec(get("table.zone.create"))["parameters"]["properties"]["description"]["description"]


def test_a_new_zone_gets_a_description_only_when_the_person_asks_for_one():
    assert "Only a description the person asks to put on the zone: empty unless they ask" in told()


def test_a_new_zone_never_gets_a_description_from_the_rest_of_the_sentence():
    assert "never written from what else they say of it (what it is for, who sits there)" in told()
