"""Input and output schemas of the flow app's operations (OpenAPI, live params, 422 per field, and the
assistant's tools: every input field carries a ``description``).

The document of an automation is a ``trigger`` and its ``steps`` (``document.py`` reads them). Every
input refuses a field it does not declare. A refusal of a step names it (``steps.<n>.<kind>.<field>``),
so the editor puts it next to the step. An automation is named by its id or its name: the assistant is
used by voice («activate the welcome automation»).

What a step names (an action, a read, an event) is checked against the apps that are active in
``services/``: a schema knows the shape, not the business.

Each id a write takes is marked with the read that names its record (``names``, base/assistant/cards.py ``REFERS``,
checked at start by ``base.E009``): the assistant's card says which automation, draft, run or question, as the person
who confirms reads it, never by the id — an automation and a draft by their name, a run by its automation and when it
started (``label``, as the History says it), a question by what it asks.
"""

from . import (
    assistant_steps as assistant_steps,
    calls as calls,
    catalog as catalog,
    drafts as drafts,
    dry_run as dry_run,
    fields as fields,
    flows as flows,
    history as history,
    questions as questions,
    recipe_flows as recipe_flows,
    runs as runs,
    steps as steps,
    stored_secrets as stored_secrets,
    triggers as triggers,
)
