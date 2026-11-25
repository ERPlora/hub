"""The device behind a print socket and the printers it prints for: those of its registration in printing and, with
the session of whoever sets up the printers, those its ``hello`` names."""

from dataclasses import dataclass, field

from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.executor import Stream

from base.ws_print.printing import DEVICE_GET, PAIRS, PRINTER_GET, _operation, _validated
from base.ws_print.refusals import _refusal_of


@dataclass(eq=False)
class Device:
    """The device behind a socket that said ``hello``."""

    ctx: OperationContext
    device_id: str
    #: The printer ids its ``hello`` named: what a session that pairs adds to its registration.
    declared: list[str]
    #: The active printers it prints for, re-read with its registration on every beat: id → function.
    printers: dict[str, str]
    #: Hand-out of each job given on this socket (``failed`` must name the hand-out it answers).
    attempts: dict[str, int] = field(default_factory=dict)
    stream: Stream | None = None
    #: Per role, the waiting jobs its last wake result showed (``_waiting``): a job not among them is news.
    waiting: dict[str, set[tuple]] = field(default_factory=dict)
    #: Jobs this device sent back to the queue itself (``failed``): waiting again, they are no news to it.
    sent_back: set[tuple] = field(default_factory=set)
    #: When its presence was last told (``time.monotonic``); ``None`` = not yet on this socket.
    announced_at: float | None = None

    @property
    def roles(self) -> list[str]:
        return sorted(set(self.printers.values()))


class DevicesMixin:
    """The printers a ``PrintSocket`` (``base.ws_print.protocol``) reaches, read with its device's registration."""

    def _reached(self, ctx: OperationContext, device_id: str, declared: list[str]) -> dict[str, str] | None:
        """The active printers the device prints for: id → function. Those of its registration in printing
        (``printing.device.get``), whatever ``declared`` says; with the session of whoever sets up the printers, the
        active ones among ``declared`` too, which its claim pairs. ``None``: a device retired, which no session pairs
        (only setting it up again brings it back), or one not set up here that this session does not pair."""
        op = _operation(DEVICE_GET)
        try:
            answer = op(ctx, _validated(DEVICE_GET, {"device": device_id}))
        except OperationError as exc:
            raise _refusal_of(exc) from exc
        registration = answer.device
        pairs = ctx.has(PAIRS)
        if registration is None and (answer.retired or not pairs):
            return None
        printers = {} if registration is None else {str(p.id): p.usage for p in registration.printers if p.is_active}
        if pairs:
            printers.update(self._declared(ctx, declared))
        return printers

    def _declared(self, ctx: OperationContext, declared: list[str]) -> dict[str, str]:
        """The active printers of this hub among ``declared``: id → function."""
        op = _operation(PRINTER_GET)
        printers = {}
        for printer_id in declared:
            try:
                printer = op(ctx, _validated(PRINTER_GET, {"printer_id": printer_id}))
            except NotFound:
                continue  # not a printer of this hub
            except OperationError as exc:
                raise _refusal_of(exc) from exc
            if printer.is_active:
                printers[str(printer.id)] = printer.usage
        return printers
