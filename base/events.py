"""Events of base (``<app>.<entity>.<fact>``): recorded by base.services in the transaction of their operation.

The registry of hubs (plan 2026-10-17, §1.5): no live query of base reacts to them yet; the outbox keeps them as
the record of what the SaaS asked of the registry.
"""

HUB_REGISTERED = "base.hub.registered"
HUB_STATE_APPLIED = "base.hub.state_applied"
HUB_CANCELLED = "base.hub.cancelled"
HUB_RESTORED = "base.hub.restored"

ALL = [HUB_REGISTERED, HUB_STATE_APPLIED, HUB_CANCELLED, HUB_RESTORED]
