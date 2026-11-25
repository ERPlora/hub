"""What a move's steps raise: a failure with its step's code, and a stop that leaves the move to the next worker."""


class MoveFailed(RuntimeError):
    """A step of a move that failed: its code (``move_<step>``) and why, in a line."""

    def __init__(self, code: str, reason: object) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code


class MoveStopped(RuntimeError):
    """The worker is stopping: the move is left as it is for the next one to go on."""
