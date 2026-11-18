"""Schemas of resetting the business's data (``base.hub.reset``, ``base.hub.reset_apply``)."""

from typing import Literal

from ninja import Schema
from pydantic import Field

from base.schemas.blueprints import BlueprintPartOut, RemovalOut


class HubResetIn(Schema):
    apps: list[str] = Field(default_factory=list, max_length=200, description="The sections (apps) to empty.")
    confirm: str = Field("", max_length=200, description="The business's name, typed exactly.")
    dry_run: bool = Field(False, description="True: only the plan, nothing is removed.")


class ResetDatasetOut(BlueprintPartOut):
    pass


class ResetSectionOut(Schema):
    id: str
    label: str
    rows: int
    datasets: list[ResetDatasetOut]


class HubResetOut(Schema):
    dry_run: bool
    confirm_with: str = Field(description="What to type to confirm: the business's name (its address without one).")
    available: bool = Field(
        description="False while the business shares its database with other hubs, so nothing can be emptied."
    )
    sections: list[ResetSectionOut] = Field(description="The apps with rows: what each one would lose.")
    apps: list[RemovalOut] = Field(
        description="Always empty: the worker empties the sections after copying the data (base.hub.dumps says how it "
        "went)."
    )
    status: Literal["planned", "copying"] = Field(
        description="planned: only the plan (dry_run). copying: asked; the business's data is being copied, then the "
        "sections chosen are emptied."
    )



class HubResetApplyIn(Schema):
    """The worker's emptying of a reset it already copied (``base.hub.reset_apply``)."""

    apps: list[str] = Field(min_length=1, max_length=200, description="The sections (apps) to empty.")


class HubResetApplyOut(Schema):
    apps: list[RemovalOut] = Field(description="What was removed of each section, and what could not be.")

