"""base.events: the names of base's own events (``<app>.<entity>.<fact>``), recorded by base.services."""

from live.operations import NAME_RE

from base import events


def test_every_event_is_named_as_the_convention_says():
    assert events.ALL == [
        "base.hub.registered",
        "base.hub.state_applied",
        "base.hub.cancelled",
        "base.hub.restored",
    ]
    assert all(NAME_RE.match(name) for name in events.ALL)
