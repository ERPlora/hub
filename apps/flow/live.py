"""Live queries of the flow app and the events that re-run them after the COMMIT."""

from live.live_registry import live

from apps.flow.events import DRAFT_EVENTS, FLOW_EVENTS, RUN_EVENTS

# A row of the list says how its last run ended: a run that starts or ends changes it.
live("flow.flow.list", on=[*FLOW_EVENTS, *RUN_EVENTS])
live("flow.flow.detail", on=[*FLOW_EVENTS, *RUN_EVENTS])
live("flow.run.list", on=RUN_EVENTS)
# A draft leaves the tray when it is used or dismissed.
live("flow.draft.list", on=DRAFT_EVENTS)
