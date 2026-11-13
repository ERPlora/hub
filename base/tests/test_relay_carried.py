"""The actors the relay passes on to what a reaction records (FLOW-F21, BASE-F114).

An app's reaction runs as the system. When the event it answers was recorded by an actor that is passed on — a recovery
from a separate copy (``base.recovery``) or one an app declares in ``carried_actors`` on its config — what the reaction
records as the system takes that actor, first and second hand, so whoever reads the outbox knows where it comes from.
What the reaction records as someone of its own keeps it, and what anyone else caused is the system's, as before.

The declaration is made here on the platform's own config, so the test names no app.
"""

import uuid

import pytest
from django.apps import apps
from django.utils import timezone
from live.context import Scope, system_context
from live.models import OutboxEvent

from base import recovery, relay, services

A = Scope("host", "a")

#: Who hears what, and what each one records in answer: a first app answers the event that starts it all, a second
#: one answers the first's, and a third records two events of its own; a fourth answers what the business itself does,
#: and a fifth answers as someone of its own.
HEARS = {
    "one.card.made": ["first", "third"],
    "first.chat.linked": ["second"],
    "two.card.made": ["fourth"],
    "three.card.made": ["fifth"],
}
ANSWERS = {
    "first": ["first.chat.linked"],
    "second": ["second.note.added"],
    "third": ["third.tag.set", "third.tag.seen"],
    "fourth": ["fourth.chat.linked"],
    "fifth": ["fifth.task.made"],
}
#: Someone of the business, as the outbox keeps who did it.
PERSON = "01a1cff9-afb1-777e-af7c-92eb9563d42d"
#: An actor of the platform's own declaration, and another of its own that the fifth app answers as.
DECLARED = "base_run:"
OWN = f"{DECLARED}01a1cff9-afb1-777e-af7c-92ec1c30390e"


@pytest.fixture(autouse=True)
def declared(monkeypatch):
    """The platform declares its ``base_run:`` actors carried, as an app does on its config."""
    monkeypatch.setattr(apps.get_app_config("base"), relay.CARRIED_ACTORS, [DECLARED], raising=False)


def listeners(event: OutboxEvent) -> list[str]:
    return HEARS.get(event.name, [])


def record(scope: Scope, name: str, actor: str) -> OutboxEvent:
    """An event in the outbox, as ``live.outbox.record_event`` writes it for a context of ``actor``."""
    return OutboxEvent.objects.create(scope_kind=scope.kind, scope_key=scope.key, name=name, payload={}, actor=actor)


def deliver(app_label: str, event: OutboxEvent) -> None:
    """A reaction as the apps' are: it runs as the system and records its own events; the fifth runs something of its
    own (an automation's step) and records as it."""
    scope = Scope(event.scope_kind, event.scope_key)
    for name in ANSWERS[app_label]:
        record(scope, name, OWN if app_label == "fifth" else system_context(scope).actor)


def taken(now) -> None:
    services.relay_take_events(now, listeners=listeners, limit=10, max_depth=relay.MAX_EVENT_DEPTH)


def delivered(now) -> None:
    while (
        services.relay_deliver_next(
            now,
            deliver=deliver,
            listeners=listeners,
            carried=relay.carried,
            max_depth=relay.MAX_EVENT_DEPTH,
            max_attempts=relay.MAX_ATTEMPTS,
            backoff=relay.backoff,
        )
        is not None
    ):
        pass


def relayed(now) -> None:
    taken(now)
    delivered(now)


def said() -> dict[str, str]:
    """Each event of the outbox and its actor, by name."""
    return dict(OutboxEvent.objects.values_list("name", "actor"))


MARKS = [
    pytest.param(f"{DECLARED}{uuid.uuid7()}", id="an actor an app declares"),
    pytest.param(recovery.actor_of(uuid.uuid7()), id="a recovery"),
]


@pytest.mark.parametrize("mark", MARKS)
def test_what_reactions_record_as_the_system_for_a_carried_actor_takes_it_first_and_second_hand(db, mark):
    record(A, "one.card.made", mark)

    relayed(timezone.now())

    assert said() == {
        "one.card.made": mark,
        "first.chat.linked": mark,
        "second.note.added": mark,
        "third.tag.set": mark,
        "third.tag.seen": mark,
    }


@pytest.mark.parametrize("mark", MARKS)
def test_what_a_reaction_records_as_someone_of_its_own_keeps_it(db, mark):
    """An automation the reaction runs does its steps as its own run: the chain grows from that run, never from the one
    before it."""
    record(A, "three.card.made", mark)

    relayed(timezone.now())

    assert said() == {"three.card.made": mark, "fifth.task.made": OWN}


@pytest.mark.parametrize(
    "actor",
    [
        pytest.param("system", id="the system"),
        pytest.param(PERSON, id="a person"),
        pytest.param("another_run:01a1cff9-afb1-777e-af7c-92ec1c30390e", id="something nobody declares"),
    ],
)
def test_what_reactions_record_for_anyone_else_is_the_system_s(db, actor):
    record(A, "one.card.made", actor)

    relayed(timezone.now())

    system = system_context(A).actor
    assert said() == {
        "one.card.made": actor,
        "first.chat.linked": system,
        "second.note.added": system,
        "third.tag.set": system,
        "third.tag.seen": system,
    }


@pytest.mark.parametrize("mark", MARKS)
def test_what_the_business_does_in_the_same_pass_never_takes_a_carried_actor(db, mark):
    """The business at work in the same pass as a carried actor's event: only what answers that event takes it, not what
    answered the business's a moment before, nor what the platform records as the system while the relay delivers."""
    record(A, "two.card.made", PERSON)
    record(A, "one.card.made", mark)
    now = timezone.now()

    taken(now)
    record(A, "two.card.seen", "system")
    delivered(now)
    relayed(now)

    system = system_context(A).actor
    assert said() == {
        "two.card.made": PERSON,
        "fourth.chat.linked": system,
        "two.card.seen": system,
        "one.card.made": mark,
        "first.chat.linked": mark,
        "second.note.added": mark,
        "third.tag.set": mark,
        "third.tag.seen": mark,
    }


@pytest.mark.parametrize(
    "actor, carried",
    [
        pytest.param(f"{DECLARED}{uuid.uuid7()}", True, id="declared"),
        pytest.param(recovery.actor_of(uuid.uuid7()), True, id="a recovery"),
        pytest.param("system", False, id="the system"),
        pytest.param(PERSON, False, id="a person"),
        pytest.param("another_run:01a1cff9-afb1-777e-af7c-92ec1c30390e", False, id="undeclared"),
        pytest.param("base_runner:x", False, id="only the declared prefix"),
    ],
)
def test_carried_says_which_actors_are_passed_on(actor, carried):
    assert relay.carried(actor) is carried


def test_a_declaration_the_check_refuses_passes_nothing_on(monkeypatch):
    """An empty prefix would pass on every actor, the system's and the business's people's: never used."""
    monkeypatch.setattr(apps.get_app_config("base"), relay.CARRIED_ACTORS, ["", DECLARED], raising=False)

    assert (relay.carried("system"), relay.carried(PERSON), relay.carried(f"{DECLARED}x")) == (False, False, False)


class TestTheDeclarationIsChecked:
    def errors(self) -> list[tuple[str, str]]:
        return [(error.id, str(error.obj.label)) for error in relay.check_carried_actors()]

    def test_what_every_app_declares_today_passes(self):
        assert self.errors() == []

    @pytest.mark.parametrize(
        "declared",
        [
            pytest.param([""], id="empty: every actor"),
            pytest.param(["system"], id="the system"),
            pytest.param(["base_run"], id="no colon at its end"),
            pytest.param(["customer_run:"], id="another app's"),
            pytest.param(["basement:"], id="a label that only starts the same"),
            pytest.param("base_run:", id="not a list"),
            pytest.param([7], id="not text"),
        ],
    )
    def test_an_app_declares_only_actors_of_its_own(self, monkeypatch, declared):
        monkeypatch.setattr(apps.get_app_config("base"), relay.CARRIED_ACTORS, declared, raising=False)

        assert self.errors() == [("base.E017", "base")]

    @pytest.mark.parametrize("declared", [["base:"], ["base_run:", "base_shift:"], []])
    def test_its_own_label_with_a_colon_or_an_underscore_passes(self, monkeypatch, declared):
        monkeypatch.setattr(apps.get_app_config("base"), relay.CARRIED_ACTORS, declared, raising=False)

        assert self.errors() == []
