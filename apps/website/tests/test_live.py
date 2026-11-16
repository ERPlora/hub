"""Live queries of the website app: the editor's site follows its saves and its publications."""

import json
from pathlib import Path

import psycopg
import pytest
from django.db import connections
from live.live_registry import live_registry
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from apps.website import events
from apps.website.tests.conftest import HUB_DB_COMMITTED, A, B, ctx_for, full_content
from base.tenancy.context import use_hub

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


# The notice after the COMMIT goes to the channel of the hub that wrote, never to another hub's editors.

WAIT = 1.0
QUIET = 0.3


@pytest.fixture
def listen(django_db_setup):
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"], user=params["USER"], password=params["PASSWORD"], host=params["HOST"], port=params["PORT"]
    )
    sessions = []

    def open_session(scope):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT, stop_after=None):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout, stop_after=stop_after)]


def recorded() -> list[tuple[str, str, str]]:
    """The website's events in the outbox of the business at work, with the scope each one names."""
    rows = OutboxEvent.objects.filter(name__startswith="website.").order_by("created_at")
    return list(rows.values_list("name", "scope_kind", "scope_key"))


@HUB_DB_COMMITTED
def test_saving_and_publishing_in_hub_b_tells_the_editors_of_b_only(listen, hub_b):
    # flow: WEBSITE-F01, WEBSITE-F07 — another hub's editor never re-reads this hub's site.
    on_a, on_b = listen(A), listen(B)
    save = get("website.site.save")
    publish = get("website.site.publish")
    with use_hub(hub_b):
        save(ctx_for(scope=B), save.input(template="classic", theme={}, content=full_content()))
        assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [events.SITE_UPDATED]})]
        assert received(on_a, timeout=QUIET) == []
        publish(ctx_for(scope=B), publish.input())
        assert received(on_b, stop_after=1) == [(channel_for(B), {"events": [events.SITE_PUBLISHED]})]
        assert received(on_a, timeout=QUIET) == []
        # What B wrote names B, in B's own outbox, and nothing of it reaches A's.
        assert recorded() == [(events.SITE_UPDATED, B.kind, B.key), (events.SITE_PUBLISHED, B.kind, B.key)]
    assert recorded() == []
    # Positive control: the same listener of A hears a save made in A.
    save(ctx_for(scope=A), save.input(template="modern", theme={}, content=full_content()))
    assert received(on_a, stop_after=1) == [(channel_for(A), {"events": [events.SITE_UPDATED]})]
    assert received(on_b, timeout=QUIET) == []
