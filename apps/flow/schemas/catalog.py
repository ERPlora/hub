"""Schemas of what an automation is built from (``flow.catalog.read``, ``flow.operation.get``): the events,
actions and reads of the active apps, and an operation by its name."""

from typing import Annotated, Literal

from ninja import Field, Schema

from apps.flow.schemas.fields import In


class OperationRefIn(In):
    operation: str = Field(max_length=96, description="The operation to name, by its registered name.")


class OperationNameOut(Schema):
    operation: str
    label: str


class CatalogIn(In):
    apps: list[Annotated[str, Field(max_length=64)]] | None = Field(
        None,
        max_length=30,
        description="Every event and action of these apps, by their id (`task`, `cash_register`).",
    )
    names: list[Annotated[str, Field(max_length=96)]] | None = Field(
        None,
        max_length=30,
        description="These events and actions, by name (`cash_register.session.closed`, `task.task.create`).",
    )
    only_names: bool = Field(
        False,
        description="The events and only the names of the actions (`action_names`), to choose which to read whole "
        "by `names`.",
    )


class CatalogEventOut(Schema):
    name: str
    app: str
    app_name: str


class FieldOut(Schema):
    name: str
    type: str
    required: bool
    description: str
    choices: list[str]


class CatalogActionOut(Schema):
    name: str
    kind: Literal["command", "query"]
    app: str
    app_name: str
    description: str
    fields: list[FieldOut]
    outputs: list[str] = Field(
        description="What a step of it leaves for the later ones, by its path below the step (`steps.<id>.<path>`): "
        "its fields, each object among them followed by what it holds (`item`, `item.unit_price`), never what is inside "
        "a list; and a read's `found` and `count`."
    )
    #: Whether «Ask the assistant» may use it (its ``ai=`` offers it to the assistant).
    assistant: bool = False
    #: Whether it needs a person's yes first: only an «Ask the assistant» step with «Ask me first» may use it.
    ask_first: bool = False


class CatalogAppOut(Schema):
    app: str
    app_name: str


class CatalogOut(Schema):
    events: list[CatalogEventOut]
    actions: list[CatalogActionOut]
    #: With ``only_names``, the actions by name alone, instead of whole in ``actions``.
    action_names: list[str] = []
    #: The installed apps that are off in the business: what a saved automation may still name (hub#1054).
    off_apps: list[CatalogAppOut]
