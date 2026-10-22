"""The website app's event vocabulary: ``website.<entity>.<fact in the past tense>``."""

import re

from live.operations import NAME_RE

from apps.website import events

PAST_FACT = re.compile(r"^website\.(site|image)\.[a-z_]+ed$")


def declared():
    return {name: value for name, value in vars(events).items() if name.isupper() and isinstance(value, str)}


def test_the_events():
    assert declared() == {
        "SITE_UPDATED": "website.site.updated",
        "SITE_PUBLISHED": "website.site.published",
        "SITE_UNPUBLISHED": "website.site.unpublished",
        "IMAGE_UPLOADED": "website.image.uploaded",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_the_website_reacts_to_no_other_app():
    assert getattr(events, "REACTIONS", {}) == {}
