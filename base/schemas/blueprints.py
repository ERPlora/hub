"""Schemas of blueprints, imports and datasets (``base.blueprint.*``, ``base.import.*``, ``base.dataset.list``)."""

import datetime as dt
from typing import Annotated, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field

from base.schemas.assistant import names


# ── Data: blueprints, imports and reset ───────────────

#: A file uploaded in base64: 20 MB of zip (``base.blueprint.archive.MAX_FILE_BYTES``) is 27 962 028 characters.
FILE_BASE64_MAX = 28_000_000
BlueprintPurpose = Literal["backup", "template"]
#: How a dataset of a load went: «applied», «partial», «already» (it was there), «failed», «empty» (nothing to copy)
#: or «discarded» (personal data in a template).
DatasetStatus = Literal["applied", "partial", "already", "failed", "empty", "discarded"]
#: How an app of a load went: a dataset's statuses, or «inactive» (not on here), «unknown» (this hub does not have it)
#: or «not_selected».
AppLoadStatus = Literal[
    "applied",
    "partial",
    "already",
    "failed",
    "empty",
    "discarded",
    "inactive",
    "unknown",
    "not_selected",
    "waiting",
    "setup_failed",
]
ImportStatus = Literal["complete", "partial", "failed"]


class BlueprintListIn(Schema):
    """No input: the catalogue for this person and this hub."""


class BlueprintAppOut(Schema):
    id: str
    label: str = Field(description="The app's name as the person reads it.")


class BlueprintPartOut(Schema):
    key: str = Field(description="«<app>.<what>»: a dataset, e.g. «inventory.product».")
    label: str
    rows: int


class TemplateOut(Schema):
    key: str = Field(description="«<vertical>.<language>».")
    name: str
    description: str
    language: str
    country: str = Field(description="ISO 3166 code: the country its taxes and prices are for.")
    vertical: str
    version: str
    apps: list[BlueprintAppOut] = Field(description="The apps it turns on: its vertical's.")
    contents: list[BlueprintPartOut] = Field(description="What it brings, by dataset.")


class BlueprintListOut(Schema):
    templates: list[TemplateOut] = Field(
        description="The hub's country first, then the person's language, then the hub's vertical."
    )
    empty: bool = Field(description="Nothing a template brings is in the business yet (the Home offers one).")


class BlueprintSourceIn(Schema):
    """A template of the catalogue or a .blueprint.zip of the person, exactly one of them."""

    template: str = Field(
        "", max_length=80, title=gettext_noop("Template"), description="«<vertical>.<language>» of the catalogue."
    )
    file_base64: str = Field(
        "",
        max_length=FILE_BASE64_MAX,
        title=gettext_noop("File"),
        description="A .blueprint.zip in base64 (20 MB at most).",
    )


class BlueprintDatasetOut(BlueprintPartOut):
    personal: bool = Field(description="Personal data: it travels in a backup only.")
    travels: bool = Field(description="False: it is left out of this load (personal data in a template).")


class BlueprintAppSummaryOut(BlueprintAppOut):
    status: Literal["on", "turns_on", "inactive", "unknown"] = Field(
        description="«on»; «turns_on»: off in this hub, the load turns it on first (with the apps it needs) and then "
        "loads it; «inactive»: off and left off (only its data names it, the plan gives no right to it or the app does "
        "not go on in this business), nothing of it loads; «unknown»: this hub does not have it."
    )
    datasets: list[BlueprintDatasetOut]


class BlueprintSummaryOut(Schema):
    name: str
    language: str
    country: str
    purpose: BlueprintPurpose
    created_at: str = Field(description="When the file was made; empty for a template of the catalogue.")
    version: str = Field(description="The template's version; empty for a file.")
    source: Literal["catalog", "file"]
    apps: list[BlueprintAppSummaryOut]
    dropped: list[str] = Field(description="Parts of the file this hub never loads (people, fiscal data…).")


class BlueprintImportIn(BlueprintSourceIn):
    apps: list[Annotated[str, Field(json_schema_extra=names("base.app.get", by="app"))]] | None = Field(
        None,
        max_length=200,
        title=gettext_noop("Apps to load"),
        description="The apps to load; none = every app of the blueprint.",
    )
    retry_of: UUID | None = Field(
        None,
        description="A load that did not go in whole: load again what did not, from the same template.",
        json_schema_extra=names("base.import.detail"),
    )


class DatasetLoadOut(Schema):
    key: str
    label: str
    status: DatasetStatus
    rows: int = Field(description="Rows the blueprint brings.")
    created: int
    already: int = Field(description="Rows already there: left as they were.")
    failed: int
    problems: list[str] = Field(description="What went wrong, the first ones, in the person's language.")


class AppLoadOut(Schema):
    id: str
    label: str
    status: AppLoadStatus
    reason: str = Field(
        "",
        description="Why an app of the blueprint that was off could not be turned on («inactive»: the plan's limit of "
        "apps, no right to it…), or how the one the load waits for goes («waiting»: being set up, its data comes by "
        "itself; «setup_failed»: it could not be set up yet), in the person's language; empty otherwise.",
    )
    datasets: list[DatasetLoadOut]


class LoadReportOut(Schema):
    status: ImportStatus
    apps: list[AppLoadOut]
    dropped: list[str]


class ImportOut(Schema):
    id: UUID
    name: str
    source: Literal["catalog", "file"]
    template_key: str
    status: ImportStatus
    created_at: dt.datetime
    created_by: str
    rows: int = Field(description="Rows it created.")
    undone: bool
    undoable: bool = Field(description="It created rows and was not undone.")
    retry: bool = Field(description="What did not go in can be loaded again.")
    retry_blocked: Literal["", "file", "version_gone", "complete", "undone", "waiting"] = Field(
        description="Why it cannot be retried: «file» (uploaded by hand), «version_gone» (the template changed), "
        "«complete» (nothing missing), «undone», «waiting» (an app is being set up: what is missing comes by itself)."
    )
    report: LoadReportOut


class ImportListIn(Schema):
    """No input: the loads of this hub, newest first."""


class ImportListOut(Schema):
    imports: list[ImportOut] = Field(description="Newest first, at most the last 50.")
    unfinished: ImportOut | None = Field(
        description="The last load, when it did not go in whole and was not undone: shown before the catalogue."
    )


class BlueprintExportIn(Schema):
    """What an export takes, flat, as a query string: the apps it registers, the ones whose data travels and, of
    those, which datasets (an app none of whose datasets is named takes all of them)."""

    name: str = Field(min_length=1, max_length=120, description="The name of the file and of the blueprint.")
    language: str = Field(min_length=2, max_length=8, description="The language of its texts (a code: «es»).")
    purpose: BlueprintPurpose = Field(
        description="«backup» (this business, its customers too) or «template» (to share: never personal data)."
    )
    apps: list[str] = Field(default_factory=list, max_length=200, description="Apps on in this hub it registers.")
    data: list[str] = Field(
        default_factory=list, max_length=200, description="Of those apps, the ones whose data travels too."
    )
    datasets: list[str] = Field(
        default_factory=list,
        max_length=200,
        description="Of those, the datasets chosen; an app none of whose datasets is named takes all.",
    )


class BlueprintFileOut(Schema):
    filename: str
    content_type: str
    content_base64: str


class DatasetListIn(Schema):
    """No input: the apps on of this hub and what of each can travel."""


class DatasetCountOut(BlueprintPartOut):
    personal: bool


class AppDatasetsOut(Schema):
    id: str
    label: str
    icon: str
    datasets: list[DatasetCountOut] = Field(description="Empty: the app travels, with nothing of its own to copy.")


class DatasetListOut(Schema):
    apps: list[AppDatasetsOut] = Field(description="By name.")


class ImportIdIn(Schema):
    """A load of this business, by its id."""

    id: UUID = Field(title=gettext_noop("Import"), json_schema_extra=names("base.import.detail"))


class ImportUndoIn(ImportIdIn):
    """A load to undo: the rows it created go."""


class RemovalOut(Schema):
    id: str
    label: str
    removed: int
    failed: int
    problems: list[str]


class ImportUndoOut(Schema):
    id: UUID
    apps: list[RemovalOut]

