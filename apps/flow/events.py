"""Events of the flow app (``flow.<entity>.<fact>``) and its reaction to every other app's events.

services.py records them in the outbox, in the command's transaction; live.py names the ones that re-run
each live query. They carry ids (and a run's status), never a name or what an event brought.

Reaction: flow is the one app that listens to EVERY event (FLOW-F21): each one may start the
automations of the business that wait for it. The outbox relay (phase 2, in the worker) hands each
delivered event to ``react`` with its id and its actor; ``flow.run.react`` runs as the system, in its
own transaction, and starts at most one run per automation and event, so a repeated delivery changes
nothing. Its own events are never handed on: no automation can start on them.
"""

from typing import Any
from uuid import UUID

from live.context import Scope, system_context
from live.operations import get

FLOW_CREATED = "flow.flow.created"
FLOW_UPDATED = "flow.flow.updated"
FLOW_ENABLED = "flow.flow.enabled"
FLOW_PAUSED = "flow.flow.paused"
FLOW_GRANTED = "flow.flow.granted"
FLOW_DELETED = "flow.flow.deleted"
RUN_STARTED = "flow.run.started"
RUN_PARKED = "flow.run.parked"
RUN_RESUMED = "flow.run.resumed"
RUN_FINISHED = "flow.run.finished"
DRAFT_PROPOSED = "flow.draft.proposed"
DRAFT_USED = "flow.draft.used"
DRAFT_DISMISSED = "flow.draft.dismissed"
SECRET_SAVED = "flow.secret.saved"
SECRET_DELETED = "flow.secret.deleted"

FLOW_EVENTS = [
    FLOW_CREATED,
    FLOW_UPDATED,
    FLOW_ENABLED,
    FLOW_PAUSED,
    FLOW_GRANTED,
    FLOW_DELETED,
]
RUN_EVENTS = [RUN_STARTED, RUN_PARKED, RUN_RESUMED, RUN_FINISHED]
DRAFT_EVENTS = [DRAFT_PROPOSED, DRAFT_USED, DRAFT_DISMISSED]
SECRET_EVENTS = [SECRET_SAVED, SECRET_DELETED]
ALL = [*FLOW_EVENTS, *RUN_EVENTS, *DRAFT_EVENTS, *SECRET_EVENTS]

#: Any event, as ``live.live_registry.ALL_EVENTS`` names it.
ANY_EVENT = "*"
#: Event of another app → the operation of this app that reacts to it: here, every event.
REACTIONS = {ANY_EVENT: "flow.run.react"}


def react(
    scope: Scope,
    name: str,
    payload: dict[str, Any],
    *,
    event_id: UUID | str,
    actor: str = "",
):
    """Start, as the system, the automations of ``scope`` that wait for the event ``name``.

    ``None`` for flow's own events, which no automation waits for.
    """
    if name.startswith("flow."):
        return None
    reaction = get(REACTIONS[ANY_EVENT])
    data = reaction.input.model_validate(
        {"event_id": event_id, "event": name, "payload": payload, "actor": actor}
    )
    return reaction(system_context(scope), data)


def deliver(event):
    """Hands an outbox event (``live.models.OutboxEvent``) to ``react``, as the relay will."""
    return react(
        Scope(event.scope_kind, event.scope_key),
        event.name,
        event.payload,
        event_id=event.id,
        actor=event.actor,
    )
