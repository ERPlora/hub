"""base.events: the names of base's own events (``<app>.<entity>.<fact>``), recorded by base.services."""

from live.operations import NAME_RE

from base import events


def test_every_event_is_named_as_the_convention_says():
    assert events.ALL == [
        "base.hub.registered",
        "base.hub.state_applied",
        "base.hub.cancelled",
        "base.hub.restored",
        "base.hub.purged",
        # A business that shared one database with others got its own (cut_shared_hubs).
        "base.hub.cut",
        "base.demo.created",
        "base.demo.code_created",
        "base.demo.expired",
        "base.demo.purged",
        # Settings › Data: a load, an undo, a reset.
        "base.blueprint.imported",
        "base.import.undone",
        "base.hub.data_reset",
        # System: the events the relay gives up on, resent or discarded.
        "base.failed_event.created",
        "base.failed_event.retried",
        "base.failed_event.discarded",
        # Files: what changes the business's files.
        "base.file.uploaded",
        "base.file.folder_created",
        "base.file.renamed",
        "base.file.moved",
        "base.file.deleted",
        # The way in.
        "base.pin.set",
        "base.device.mode_changed",
        "base.device.renamed",
        "base.device.removed",
        "base.device.pruned",
        "base.access.settings_changed",
        "base.profile.updated",
        # People and permissions: a PIN taken away, a badge given or taken away.
        "base.person.pin_removed",
        "base.person.badge_set",
        "base.person.badge_removed",
        # The business's API keys.
        "base.api_key.created",
        "base.api_key.rotated",
        "base.api_key.revoked",
        # A manager's approval given, and spent.
        "base.approval.granted",
        "base.approval.used",
        # The API's documentation shown or hidden.
        "base.api_doc.settings_changed",
        # An app turned on or off by the business.
        "base.app.enabled",
        "base.app.disabled",
        # An app whose tables a hub's own database is getting, and making them failing.
        "base.app.activation_requested",
        "base.app.activation_failed",
    ]
    assert all(NAME_RE.match(name) for name in events.ALL)
