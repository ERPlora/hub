"""Events of base (``<app>.<entity>.<fact>``): recorded by base.services in the transaction of their operation.

The registry of hubs (plan 2026-10-17, §1.5) and its demos (§1.6, §1.7): no live query of base reacts to them yet;
the outbox keeps them as the record of what the SaaS asked of the registry and of what the reaper purged.
"""

HUB_REGISTERED = "base.hub.registered"
HUB_STATE_APPLIED = "base.hub.state_applied"
HUB_CANCELLED = "base.hub.cancelled"
HUB_RESTORED = "base.hub.restored"
DEMO_CREATED = "base.demo.created"
#: A one-time code into a demo was made; the event names the demo, never the code.
DEMO_CODE_CREATED = "base.demo.code_created"
DEMO_EXPIRED = "base.demo.expired"
DEMO_PURGED = "base.demo.purged"

# ── Data: blueprints, imports and reset (APP-BASE-2) ──
#: A blueprint was loaded (BASE-G105): its load's id and how it went. The Home and the loads read themselves again.
BLUEPRINT_IMPORTED = "base.blueprint.imported"
#: A load was undone (BASE-G108): its id.
IMPORT_UNDONE = "base.import.undone"
#: Every row of the apps named was removed (BASE-G109).
HUB_DATA_RESET = "base.hub.data_reset"
#: What Settings › Data does to the business: the Home's queries follow them (BASE-G131).
DATA_EVENTS = (BLUEPRINT_IMPORTED, IMPORT_UNDONE, HUB_DATA_RESET)

ALL = [
    HUB_REGISTERED,
    HUB_STATE_APPLIED,
    HUB_CANCELLED,
    HUB_RESTORED,
    DEMO_CREATED,
    DEMO_CODE_CREATED,
    DEMO_EXPIRED,
    DEMO_PURGED,
    *DATA_EVENTS,
]
