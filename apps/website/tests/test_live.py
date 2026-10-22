"""Live queries of the website app: the editor's site follows its saves and its publications."""

from pathlib import Path

from live.live_registry import live_registry

from apps.website import events

EVENTS_SOURCE = Path(events.__file__).read_text()


def website_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("website.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_the_site_follows_its_saves_and_its_publications():
    assert website_queries() == {
        "website.site.get": ["website.site.updated", "website.site.published", "website.site.unpublished"],
    }


def test_every_event_is_a_literal_of_events_py():
    for on in website_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event


def test_an_upload_re_runs_nothing():
    assert not {name for name in live_registry.affected([events.IMAGE_UPLOADED]) if name.startswith("website.")}
