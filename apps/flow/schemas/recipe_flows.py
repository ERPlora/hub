"""Schemas of the factory recipes (``flow.recipe.*``, FLOW-F33 to F36): the ready-made automations the
apps bring."""

from typing import Annotated, Any
from uuid import UUID

from ninja import Field, Schema
from pydantic import StringConstraints

from apps.flow.schemas.fields import In
from apps.flow.schemas.flows import FlowOut
from base.schemas.assistant import ReadOn

RecipeRef = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,46}/[a-z][a-z0-9_]{0,47}$")]


class RecipeListIn(In):
    offset: ReadOn = 0


class RecipeRefIn(In):
    recipe: RecipeRef = Field(
        description="The ready-made automation an app brings, as `<app>/<id>` («appointment/customer_cancelled»): "
        "`flow.recipe.list` gives them."
    )


class RecipeGrantOut(Schema):
    operation: str
    reason: str = Field(description="Why it asks for it, in the words of the app that brings it.")


class RecipeInstalledOut(Schema):
    flow_id: UUID
    name: str
    enabled: bool
    outdated: bool = Field(description="Its app brings a newer version than the one it was built or restored from.")
    missing_grants: list[str]
    repair: dict[str, dict[str, Any]] = Field(
        description="The «Only when…» clauses its app added since the version it was built from; empty: nothing to repair."
    )


class RecipeOut(Schema):
    ref: str = Field(description="`<app>/<id>`: what `flow.recipe.enable` and the others take.")
    app: str
    app_name: str
    icon: str
    id: str
    name: str
    summary: str
    description: str
    trigger: dict[str, Any]
    steps: list[dict[str, Any]]
    grants: list[RecipeGrantOut]
    installed: RecipeInstalledOut | None = Field(description="The automation this business built from it, if any.")


class RecipeSetAsideOut(Schema):
    ref: str
    app: str
    app_name: str
    name: str
    code: str = Field(description="`flow.recipe_needs_apps` or `flow.recipe_invalid`.")
    message: str
    apps: list[str] = Field(description="The apps it needs that this business does not have.")


class RecipeListOut(Schema):
    recipes: list[RecipeOut]
    set_aside: list[RecipeSetAsideOut]


class RecipeEnabledOut(Schema):
    created: bool = Field(description="true: it was built now; false: it already existed and was switched on.")
    flow: FlowOut
