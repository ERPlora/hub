"""Read operations of the flow app (``READ ONLY``) and the helpers the writes and the engine share.

- **The catalog** (``catalog_events``, ``catalog_operations``): what the active apps declare, never a
  name made up here. Events are each app's ``events.ALL``; actions and reads are its registered
  operations whose permission the app declares (a person can be granted it: platform-only reactions
  are left out). ``active_apps`` asks ``base.apps_on.active_apps`` for the business's active apps, the same
  activation and entitlement check the relay and the operation gate use.
- **Values** (``map_params``): a step's params for what the run knows (``document.resolve``), leaving out
  what came out empty, so an optional field keeps its default. What a person reads (``PERSON_PARAMS``, a question's
  texts) says each datum in words (``words_for``); what goes to a machine, as the code keeps it.
- **«Try it»** (``flow.flow.test``) walks the steps against the last real event of this business and
  executes nothing: it validates each action's data against the action's own schema.
- **One record by its id** (an automation, a draft, a run, a question waiting for an answer), with the words its
  screen names it by: what the assistant's card says instead of the id (schemas.py, ``names``).
"""

from . import (
    catalog as catalog,
    drafts as drafts,
    dry_run as dry_run,
    flows as flows,
    pinned as pinned,
    problems as problems,
    questions as questions,
    reads as reads,
    reasons as reasons,
    recipe_flows as recipe_flows,
    runs as runs,
    stored_secrets as stored_secrets,
    values as values,
)
