"""Live queries of the demo app: which events re-run which query."""

from pathlib import Path

from live.live_registry import live_registry

from apps.demo import events

EVENTS_SOURCE = (Path(events.__file__)).read_text()
ALL_FOUR = ["demo.item.created", "demo.item.updated", "demo.item.deleted", "demo.item.line_added"]


def demo_queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("demo.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_query_and_its_events():
    assert demo_queries() == {
        "demo.item.list": ALL_FOUR,
        "demo.item.detail": ["demo.item.updated", "demo.item.deleted", "demo.item.line_added"],
        "demo.item.stats": ALL_FOUR,
    }


def test_every_event_is_a_literal_of_events_py():
    for on in demo_queries().values():
        for event in on:
            assert f'"{event}"' in EVENTS_SOURCE, event


def test_a_new_line_re_runs_the_list_the_detail_and_the_stats():
    assert live_registry.affected([events.ITEM_LINE_ADDED]) >= {"demo.item.list", "demo.item.detail", "demo.item.stats"}


def test_a_new_item_does_not_re_run_a_detail():
    assert "demo.item.detail" not in live_registry.affected([events.ITEM_CREATED])
