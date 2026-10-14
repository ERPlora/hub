"""The customer app's event vocabulary: ``customer.<entity>.<fact>``, recorded by services.py."""

from live.operations import NAME_RE

from apps.customer import events


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str)
    }


def test_the_events():
    assert declared() == {
        "CUSTOMER_CREATED": "customer.customer.created",
        "CUSTOMER_UPDATED": "customer.customer.updated",
        "CUSTOMER_GROUPS_CHANGED": "customer.customer.groups_changed",
        "CUSTOMER_TAGS_CHANGED": "customer.customer.tags_changed",
        "CUSTOMER_DELETED": "customer.customer.deleted",
        "CUSTOMER_MERGED": "customer.customer.merged",
        "CUSTOMER_ERASED": "customer.customer.erased",
        "NOTE_ADDED": "customer.note.added",
        "ACTIVITY_RECORDED": "customer.activity.recorded",
        "CONSENT_GRANTED": "customer.consent.granted",
        "CONSENT_WITHDRAWN": "customer.consent.withdrawn",
        "ORDER_LINKED": "customer.order.linked",
        "ORDER_UNLINKED": "customer.order.unlinked",
        "PURCHASE_RECORDED": "customer.purchase.recorded",
        "PURCHASE_VOIDED": "customer.purchase.voided",
        "GROUP_CREATED": "customer.group.created",
        "GROUP_UPDATED": "customer.group.updated",
        "GROUP_DELETED": "customer.group.deleted",
        "TAG_CREATED": "customer.tag.created",
        "TAG_UPDATED": "customer.tag.updated",
        "TAG_DELETED": "customer.tag.deleted",
        "FIELD_CREATED": "customer.field.created",
        "FIELD_UPDATED": "customer.field.updated",
        "FIELD_DELETED": "customer.field.deleted",
    }


def test_every_event_is_app_entity_fact():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert value.startswith("customer."), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())
