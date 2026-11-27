"""The values of a closed list the assistant still tells the model as codes only shrink.

``base/tests/assistant_closed_lists_known.json`` lists, by tool and by path, the values of an answer no screen names
yet (``unnamed``). A tool that answers a new one is named (its field's ``choices``, its app's ``LiveAppConfig.choices``
or a ``choices_of`` mark), never added to that list: compared with where the branch left main, the list has no value
it did not have there. Its other part (``undeclared``) is not an exception: those lists reach the model with their
names, and a new tool may add to it.
"""

import json

from allow_list_base import REPO, file_at_base

KNOWN_FILE = "base/tests/assistant_closed_lists_known.json"

Unnamed = dict[str, dict[str, list[str]]]


def grown(now_text: str, base_text: str | None) -> list[str]:
    """Each value the file lists now that it did not at the base, as ``tool: path: value``; none where the file is
    new, which is the list being born."""
    if base_text is None:
        return []
    before: Unnamed = json.loads(base_text)["unnamed"]
    now: Unnamed = json.loads(now_text)["unnamed"]
    return sorted(
        f"{tool}: {path}: {value}"
        for tool, paths in now.items()
        for path, values in paths.items()
        for value in values
        if value not in before.get(tool, {}).get(path, ())
    )


def as_file(unnamed: Unnamed) -> str:
    return json.dumps({"unnamed": unnamed, "undeclared": {}})


def test_a_value_a_tool_or_a_path_added_to_the_list_is_found_and_one_taken_off_is_not():
    before = {"demo.item.list": {"rows[].status": ["done", "open"], "kind": ["one"]}, "demo.item.get": {"status": ["open"]}}
    now = {
        "demo.item.list": {"rows[].status": ["done", "open", "zzz_new"], "best.status": ["open"]},
        "demo.thing.figures": {"status": ["zzz_new"]},
    }
    assert grown(as_file(now), as_file(before)) == [
        "demo.item.list: best.status: open",
        "demo.item.list: rows[].status: zzz_new",
        "demo.thing.figures: status: zzz_new",
    ]
    assert grown(as_file(before), as_file(before)) == []
    assert grown(as_file(now), None) == []


def test_the_values_the_assistant_tells_as_codes_only_shrink():
    found = grown((REPO / KNOWN_FILE).read_text(), file_at_base(KNOWN_FILE))
    assert not found, (
        f"New in {KNOWN_FILE}; the list only shrinks, so name the value as its screens do instead:\n" + "\n".join(found)
    )
