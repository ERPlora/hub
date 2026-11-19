"""What ``base.health.list`` answers: the Home's health row (``base.home_health``)."""

from typing import Literal

from ninja import Schema
from pydantic import Field


class HealthListIn(Schema):
    """No input: what the apps on in this business say of their own, for who runs it."""


class HealthItemOut(Schema):
    key: str = Field(description="The app's label: one item per app.")
    app: str
    state: Literal["ok", "no_signal", "not_configured", "unknown"] = Field(
        description="ok: it works; no_signal: it is set up but does not answer; not_configured: it is not set up; "
        "unknown: it could not be checked (never ok, and nothing for the person to do)."
    )
    title: str = Field(description="What the app says of that state, in the person's language.")
    action: str | None = Field(description="What fixes it, for no_signal and not_configured; null otherwise.")
    route: str | None = Field(description="The screen of the app where it is fixed, with the action; null otherwise.")


class HealthListOut(Schema):
    items: list[HealthItemOut]
