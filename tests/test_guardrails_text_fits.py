"""The sites the e2e check of cut texts already knows only shrink.

``tests/e2e/text-fits-known.json`` lists the boxes that ``screens-text-fits.spec.ts`` lets cut a text, each with the
screens it cuts on and the issue that fixes it. The spec fails when a known site no longer cuts on one of its screens,
so the list goes down as the sites are fixed; this test fails when a branch adds a box, or a screen to a box, that the
list did not have where the branch left origin/main: a text cut somewhere new is fixed, not listed.
"""

import json
import re

from allow_list_base import REPO, file_at_base

KNOWN = "tests/e2e/text-fits-known.json"


def pairs(text: str) -> set[tuple[str, str]]:
    """Each box with each screen it is known to cut on."""
    return {(site["box"], screen) for site in json.loads(text) for screen in site["screens"]}


def grown(now: str, before: str | None) -> list[str]:
    """The boxes and screens in ``now`` that ``before`` did not know; nothing while there was no list before."""
    if before is None:
        return []
    return sorted(f"{box} on {screen}" for box, screen in pairs(now) - pairs(before))


def site(box: str, *screens: str) -> dict[str, object]:
    return {"box": box, "screens": list(screens), "issue": "ERPlora/hub#1", "what": "a title"}


def test_a_box_or_a_screen_the_list_did_not_know_is_refused():
    before = json.dumps([site("h1.title", "/a")])
    assert grown(before, before) == []
    assert grown(json.dumps([]), before) == []
    assert grown(json.dumps([site("h1.title", "/a", "/b")]), before) == ["h1.title on /b"]
    assert grown(json.dumps([site("h1.title", "/a"), site("span.name", "/a")]), before) == ["span.name on /a"]
    assert grown(json.dumps([site("span.name", "/a")]), None) == []


def test_the_known_sites_only_shrink():
    now = (REPO / KNOWN).read_text(encoding="utf-8")
    assert grown(now, file_at_base(KNOWN)) == [], "fix the text cut there rather than list it"


def test_each_known_site_says_what_it_is_and_names_its_issue():
    for known in json.loads((REPO / KNOWN).read_text(encoding="utf-8")):
        assert re.fullmatch(r"ERPlora/hub#\d+", known["issue"]), known
        assert known["what"].strip(), known
        assert known["screens"], known
