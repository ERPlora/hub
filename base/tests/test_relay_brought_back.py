"""What the relay hands over of what a recovery from a separate copy brought back (BASE-F114, FLOW-F21).

An app's reaction runs as the system. What it records in answer to an event a recovery recorded came back too, so
it keeps the recovery's mark (``base.recovery.actor_of``) however deep the chain goes, and nothing that hears it treats
it as new. What any other actor caused is recorded by the system, as before.
"""

import uuid

import pytest
from django.utils import timezone
from live.context import Scope, system_context
from live.models import OutboxEvent

from base import recovery, relay, services

A = Scope("host", "a")

#: Who hears what, and what each one records in answer: a first app answers the event that starts it all, a second
#: one answers the first's, and a third records two events of its own; a fourth answers what the business itself does.
HEARS = {"one.card.restored": ["first", "third"], "first.chat.linked": ["second"], "two.card.created": ["fourth"]}
ANSWERS = {
    "first": ["first.chat.linked"],
    "second": ["second.note.added"],
    "third": ["third.tag.set", "third.tag.seen"],
    "fourth": ["fourth.chat.linked"],
}
#: Someone of the business, as the outbox keeps who did it.
PERSON = "01a1cff9-afb1-777e-af7c-92eb9563d42d"


def listeners(event: OutboxEvent) -> list[str]:
    return HEARS.get(event.name, [])


def record(scope: Scope, name: str, actor: str) -> OutboxEvent:
    """An event in the outbox, as ``live.outbox.record_event`` writes it for a context of ``actor``."""
    return OutboxEvent.objects.create(scope_kind=scope.kind, scope_key=scope.key, name=name, payload={}, actor=actor)


def deliver(app_label: str, event: OutboxEvent) -> None:
    """A reaction as the apps' are: it runs as the system and records its own events."""
    scope = Scope(event.scope_kind, event.scope_key)
    for name in ANSWERS[app_label]:
        record(scope, name, system_context(scope).actor)


def taken(now) -> None:
    """The relay's first step: the events nobody took yet get their deliveries."""
    services.relay_take_events(now, listeners=listeners, limit=10, max_depth=relay.MAX_EVENT_DEPTH)


def delivered(now) -> None:
    """The relay's second step, until nothing is due."""
    while (
        services.relay_deliver_next(
            now,
            deliver=deliver,
            listeners=listeners,
            max_depth=relay.MAX_EVENT_DEPTH,
            max_attempts=relay.MAX_ATTEMPTS,
            backoff=relay.backoff,
        )
        is not None
    ):
        pass


def relayed(now) -> None:
    """The relay's two steps, as ``base.relay.run`` takes them."""
    taken(now)
    delivered(now)


def said() -> dict[str, str]:
    """Each event of the outbox and its actor, by name."""
    return dict(OutboxEvent.objects.values_list("name", "actor"))


def test_what_reactions_record_for_what_a_recovery_brought_back_keeps_its_mark_first_and_second_hand(db):
    mark = recovery.actor_of(uuid.uuid7())
    record(A, "one.card.restored", mark)

    relayed(timezone.now())

    assert said() == {
        "one.card.restored": mark,
        "first.chat.linked": mark,
        "second.note.added": mark,
        "third.tag.set": mark,
        "third.tag.seen": mark,
    }
    assert all(recovery.brought_back(actor) for actor in said().values())


@pytest.mark.parametrize(
    "actor",
    [
        pytest.param("system", id="the system"),
        pytest.param(PERSON, id="a person"),
        pytest.param("another_run:01a1cff9-afb1-777e-af7c-92ec1c30390e", id="something else that runs"),
    ],
)
def test_what_reactions_record_for_anything_else_is_the_system_s_as_before(db, actor):
    record(A, "one.card.restored", actor)

    relayed(timezone.now())

    system = system_context(A).actor
    assert said() == {
        "one.card.restored": actor,
        "first.chat.linked": system,
        "second.note.added": system,
        "third.tag.set": system,
        "third.tag.seen": system,
    }



def test_what_the_business_does_while_a_recovery_is_handed_over_never_takes_its_mark(db):
    """The business at work in the same pass as a recovery: only what answers the recovery's event takes its mark, not
    what answered the business's a moment before, nor what the business records while the relay delivers."""
    mark = recovery.actor_of(uuid.uuid7())
    record(A, "two.card.created", PERSON)
    record(A, "one.card.restored", mark)
    now = timezone.now()

    taken(now)
    record(A, "two.card.seen", PERSON)
    delivered(now)
    relayed(now)

    system = system_context(A).actor
    assert said() == {
        "two.card.created": PERSON,
        "fourth.chat.linked": system,
        "two.card.seen": PERSON,
        "one.card.restored": mark,
        "first.chat.linked": mark,
        "second.note.added": mark,
        "third.tag.set": mark,
        "third.tag.seen": mark,
    }
