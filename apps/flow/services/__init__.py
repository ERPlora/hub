"""Write operations of the flow app, and the engine that runs the automations.

One operation = one transaction, with its events in the outbox. A write on an automation locks its row
(``select_for_update``) before it looks at it, so two saves, or a save and a run, wait for each other.
What a document names (an event, an action, a read) is checked against the active apps
(``queries.problems.catalog_problems``) and refused by field; nothing fails in silence.

**The engine.** A run starts in ``flow.run.react`` (an event of another active app), ``flow.schedule.fire_due``
(a schedule or a date), ``flow.flow.run`` (by hand) and goes on in ``flow.run.resume_due`` (after a
wait). Its steps run in order, in the same transaction, each one an operation of another app nested in
a savepoint: a step that fails leaves nothing of its own and stops the run with its reason; the steps
before it stay. A step runs only if the automation was granted its operation, with the context
``flow_run:<id>`` (what it does carries that reference in the outbox) and the system's permissions,
in the language of whoever saved the automation. One run per automation and trigger key (the outbox
event's id): the row lock and the unique constraint make a repeated delivery start nothing. A run
started by an event that a run of the same automation caused, or by a chain of more than
``document.MAX_CHAIN`` automations, stops before doing anything (``flow.loop_stopped``). An event that a recovery
from a separate copy recorded (``base.recovery.brought_back``: its actor) starts none: what came back is nothing new to
the business (BASE-F114, hub#1307).
"""

from . import (
    assistant_steps as assistant_steps,
    calls as calls,
    drafts as drafts,
    engine as engine,
    flow_document as flow_document,
    flows as flows,
    history as history,
    questions as questions,
    recipe_flows as recipe_flows,
    runs as runs,
    stored_secrets as stored_secrets,
    writes as writes,
)
