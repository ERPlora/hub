"""base.events: the names of base's own events (``<app>.<entity>.<fact>``), recorded by base.services."""

from live.operations import NAME_RE

from base import events


def test_every_event_is_named_as_the_convention_says():
    assert events.ALL == [
        "base.hub.registered",
        "base.hub.state_applied",
        "base.hub.cancelled",
        "base.hub.restored",
        "base.demo.created",
        "base.demo.code_created",
        "base.demo.expired",
        "base.demo.purged",
        # Settings › Data (APP-BASE-2): a load, an undo, a reset.
        "base.blueprint.imported",
        "base.import.undone",
        "base.hub.data_reset",
        # System (APP-BASE-7): the events the relay gives up on, resent or discarded.
        "base.failed_event.created",
        "base.failed_event.retried",
        "base.failed_event.discarded",
        # The way in (APP-BASE-3).
        "base.pin.set",
        "base.device.mode_changed",
        "base.device.renamed",
        "base.device.removed",
        "base.device.pruned",
        "base.access.settings_changed",
        "base.profile.updated",
    ]
    assert all(NAME_RE.match(name) for name in events.ALL)
