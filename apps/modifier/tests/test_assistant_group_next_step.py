"""What the assistant reads of a modifier group it has just created: what the group still needs before the till asks
for it, which of its own tools do that and on which screen the person does it.

hub#2210: after creating «Punto de la carne» and «Extras», the assistant told the owner to link them to the dishes in
Inventory's catalogue, where no form has modifiers, or said it could not do it itself. Applying a group is not among
the tools a request to create one is offered, so the model guessed the next step: the description of the create
names it, the tools that do it and the screen where it is done."""

import re

from django.apps import apps
from live import assistant as shared
from live.operations import get, registry

from base import assistant

CREATE = "modifier.group.create"
#: An operation named the way the descriptions name another tool: ``<app>.<entity>.<action>``.
OPERATION = re.compile(r"\b[a-z_]+\.[a-z_]+\.[a-z_]+\b")
#: A screen of the Hub, named by its path.
SCREEN = re.compile(r"\(\s*(/[a-z_/-]+)\s*\)")


def test_creating_a_group_names_the_tools_that_finish_it():
    """A new group has no options and applies to nothing: both are writes the assistant has, named so that it offers
    them, and the search that brings them when they are not at hand."""
    text = " ".join(shared.description(get(CREATE)).split())
    cited = set(OPERATION.findall(text))

    assert "You can do both: offer it." in text
    assert {"modifier.option.create", "modifier.link.attach", "base.assistant.find_tools"} <= cited
    for name in cited:
        assert name in registry, f"{CREATE} names {name}, which is no operation"
    assert assistant.tools.is_tool(get("modifier.option.create"))
    assert assistant.tools.is_tool(get("modifier.link.attach"))


def test_creating_a_group_sends_the_person_to_the_modifiers_screen_only():
    """Where the person applies a group is the group's own sheet, on the screen of Modifiers: the description cites
    that path and no screen of another app, and it tells that a product's own form in Inventory has no groups."""
    text = " ".join(shared.description(get(CREATE)).split())
    screens = SCREEN.findall(text)
    own = {item.path for item in apps.get_app_config("modifier").navigation}

    assert screens
    assert set(screens) <= own
    assert "a product's own form has none." in text
