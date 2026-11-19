"""Which apps are on in a business. It imports neither the relay nor the writes or reads of base, so each of them, and
the blueprints that ``base.services`` loads, can ask it whichever of them loads first."""

from live.context import Scope
from live.meta import all_live_app_configs

from base import activation, entitlement


def active_apps(scope: Scope) -> frozenset[str]:
    """The apps that are on in ``scope``: every installed app of ours but those its business has no right to
    (``base.entitlement``: a paid module without it in the SaaS's photo) and those it turned off (``base.activation``)."""
    left_out = entitlement.blocked_apps(scope) | activation.off_apps(scope)
    return frozenset(config.label for config in all_live_app_configs() if config.label not in left_out)
