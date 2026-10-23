"""The payment app's event vocabulary: ``payment.<entity>.<fact in the past tense>``.

The old module's five payment events keep their facts (``payments.payment.created`` → ``payment.payment.
created``…); the method events are new, with the method screen (PAYMENT-F08). The app reacts to no
event of another app.
"""

import re

from live.operations import NAME_RE

from apps.payment import events

#: A fact in the past: «-ed», or «sent» (irregular, the old module's own word).
PAST_FACT = re.compile(r"^payment\.(payment|method)\.([a-z_]+ed|sent)$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str)
    }


def test_the_nine_events():
    assert declared() == {
        "PAYMENT_CREATED": "payment.payment.created",
        "PAYMENT_APPROVED": "payment.payment.approved",
        "PAYMENT_SENT": "payment.payment.sent",
        "PAYMENT_COMPLETED": "payment.payment.completed",
        "PAYMENT_CANCELLED": "payment.payment.cancelled",
        "METHOD_CREATED": "payment.method.created",
        "METHOD_UPDATED": "payment.method.updated",
        "METHOD_DEACTIVATED": "payment.method.deactivated",
        "METHOD_ACTIVATED": "payment.method.activated",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_the_events_are_grouped_by_entity():
    assert events.PAYMENT_EVENTS == [
        events.PAYMENT_CREATED,
        events.PAYMENT_APPROVED,
        events.PAYMENT_SENT,
        events.PAYMENT_COMPLETED,
        events.PAYMENT_CANCELLED,
    ]
    assert events.METHOD_EVENTS == [
        events.METHOD_CREATED,
        events.METHOD_UPDATED,
        events.METHOD_DEACTIVATED,
        events.METHOD_ACTIVATED,
    ]
    assert events.ALL == events.PAYMENT_EVENTS + events.METHOD_EVENTS


def test_it_listens_to_nobody():
    assert not hasattr(events, "react")


def test_automations_offer_every_event_as_a_trigger():
    """What the app declares is what an automation can start with (PAYMENT-F07; the old module declared
    nothing, so its events never reached the catalogue: payments#16)."""
    from apps.flow.queries import catalog_events

    offered = {name for name, config in catalog_events().items() if config.label == "payment"}
    assert offered == set(declared().values())
