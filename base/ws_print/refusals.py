"""A refusal of the print channel: the ``error`` frame it sends, and the refusal an operation's failure becomes."""

from live.errors import OperationError

from base.operations import HostClosed

#: Refusals no retry fixes: the socket is closed after them.
FATAL_OPERATION_CODES = frozenset({"permission_denied", "app_inactive", "app_entitlement_blocked"})


class Refusal(Exception):
    """A refusal sent as an ``error`` frame; a fatal one closes the socket with ``4000 + status``."""

    def __init__(self, code: str, message: str, *, status: int, fatal: bool = True, fields: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.fatal, self.fields = code, message, status, fatal, fields

    def frame(self) -> dict:
        frame = {"type": "error", "code": self.code, "message": self.message}
        if self.fields:
            frame["fields"] = self.fields
        return frame


def _refusal_of(exc: OperationError) -> Refusal:
    """An operation's refusal as a frame, with the code it carries over HTTP (``unauthenticated`` for 401, the old
    hub's); a refusal no retry fixes closes the socket, as a hub that stopped serving does (the gate's code)."""
    error = exc.envelope()["error"]
    if exc.status == 401:
        return Refusal("unauthenticated", str(error["message"]), status=401)
    return Refusal(
        error["code"],
        str(error["message"]),
        status=exc.status,
        fatal=isinstance(exc, HostClosed) or error["code"] in FATAL_OPERATION_CODES,
        fields=error.get("fields"),
    )
