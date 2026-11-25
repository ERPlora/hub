"""The presence of a print host: its ``hello`` and every ``beat`` tell the command an app declares in
``print_presence`` that the device is there; ``base.E006`` checks that declaration at start."""

import logging
import time
from typing import Any

from django.core import checks
from live.meta import all_live_app_configs
from live.operations import UnknownOperation, get

# Its lines keep the name the channel always logged under, whichever module of the package writes them.
logger = logging.getLogger("base.ws_print")

#: How often a connected device beats, told in ``ready`` and ``beat`` (the old hub's ``HEARTBEAT_SECONDS``).
HEARTBEAT_SECONDS = 30
#: The least time between two presences told of one device (``print_presence``): half a beat, so a device beating at
#: the rate it is told is told about at every beat, and one beating faster writes no more than every 15 s.
PRESENCE_SECONDS = HEARTBEAT_SECONDS / 2
#: The attribute of a ``LiveAppConfig`` naming the command told of a print host's presence.
PRESENCE_ATTRIBUTE = "print_presence"


class PresenceMixin:
    """The presence told by a ``PrintSocket`` (``base.ws_print.protocol``) for its device."""

    def _announce(self) -> None:
        """Tell the declared presence (``print_presence``) that the device is there, once per :data:`PRESENCE_SECONDS`.

        A presence that fails is logged and the socket goes on: the device still prints, and its next beat tells it
        again.
        """
        name = presence_operation()
        device = self.device
        if name is None:
            return
        now = time.monotonic()
        if device.announced_at is not None and now - device.announced_at < PRESENCE_SECONDS:
            return
        try:
            self._run(name, {"device": device.device_id})
        except Exception:
            logger.warning("The presence of print host %s failed (%s); the socket goes on.", device.device_id, name, exc_info=True)
            return
        device.announced_at = now


def presence_operation() -> str | None:
    """The command told of a print host's presence: what an app declares in ``print_presence``, or ``None``."""
    for config in all_live_app_configs():
        name = getattr(config, PRESENCE_ATTRIBUTE, None)
        if name:
            return name
    return None


@checks.register("base")
def check_print_presence(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    """``base.E006``: ``print_presence`` names a command of the declaring app whose input takes ``device``, and one app
    at most declares it (the socket tells one presence)."""
    errors: list[checks.CheckMessage] = []
    declared = [config for config in all_live_app_configs() if getattr(config, PRESENCE_ATTRIBUTE, None) is not None]
    hint = (
        'Declare print_presence = "<app>.<entity>.<action>" on the LiveAppConfig of the app that keeps the print hosts: '
        "a command of its own services.py whose input takes device."
    )
    for config in declared:
        problem = _presence_problem(config, getattr(config, PRESENCE_ATTRIBUTE))
        if problem:
            errors.append(checks.Error(f"{config.label}'s print_presence {problem}.", hint=hint, obj=config, id="base.E006"))
    if len(declared) > 1:
        labels = ", ".join(sorted(config.label for config in declared))
        errors.append(
            checks.Error(f"print_presence is declared by {labels}: one app at most tells it.", hint=hint, id="base.E006")
        )
    return errors


def _presence_problem(config, name: Any) -> str | None:
    """Why ``name`` is no presence ``config`` may declare, or ``None``."""
    if not isinstance(name, str):
        return f"is {name!r}, not the name of an operation"
    try:
        op = get(name)
    except UnknownOperation:
        return f"names {name}, which is no operation"
    if op.app_label != config.label:
        return f"names {name}, an operation of another app"
    if op.kind != "command":
        return f"names {name}, a {op.kind}: the presence is a write"
    if "device" not in op.input.model_fields:
        return f"names {name}, whose input takes no device"
    return None
