"""What a tool's parameters tell the model is said once: every call carries them whole, so a paragraph pasted into
several fields of the same tool is paid for on every call, as many times as it is pasted."""

from collections import Counter

import pytest
from live import assistant as shared
from live.operations import registry

#: Longer than a short phrase. A short phrase of an inherited field (a line's quantity, its notes) repeats in every
#: model that has it, as pydantic writes each model whole: that one is not pasted.
PARAGRAPH = 80


def descriptions(node: object) -> list[str]:
    if isinstance(node, list):
        return [text for item in node for text in descriptions(item)]
    if not isinstance(node, dict):
        return []
    own = [node["description"]] if isinstance(node.get("description"), str) else []
    return own + [text for value in node.values() for text in descriptions(value)]


def said_more_than_once(name: str) -> dict[str, int]:
    said = Counter(descriptions(shared.tool_spec(registry[name])["parameters"]))
    return {text[:60]: times for text, times in said.items() if len(text) >= PARAGRAPH and times > 1}


TOOLS = sorted(name for name, op in registry.items() if shared.is_tool(op))


@pytest.mark.parametrize("name", TOOLS)
def test_a_tool_says_each_paragraph_of_its_parameters_once(name):
    assert said_more_than_once(name) == {}
