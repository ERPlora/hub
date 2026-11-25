"""What a caller (screen, assistant, API key) may send to Appointments: the fields an input refuses."""

import uuid

from pydantic import ValidationError

ID = str(uuid.uuid7())
MONDAY = "2026-10-19"


def errors(schema, **data) -> dict[str, str]:
    """The fields ``schema`` refuses in ``data``, with the first message of each (``__all__`` for the whole)."""
    try:
        schema.model_validate(data)
    except ValidationError as exc:
        out: dict[str, str] = {}
        for error in exc.errors():
            out.setdefault(
                ".".join(str(part) for part in error["loc"]) or "__all__", error["msg"]
            )
        return out
    return {}
