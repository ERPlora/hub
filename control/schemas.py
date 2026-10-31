"""What control's operations take and give: the database clusters of the Hub admin (round 2026-10-30b of PLAN-DB,
decision 1; tranche S7). Their bounds are the model's (``control.models.Cluster``), so any caller, not only the
admin's form, is held to them."""

from uuid import UUID

from ninja import Schema
from pydantic import Field, field_validator

#: The largest value of a ``PositiveIntegerField`` (Postgres' ``integer``).
INTEGER_MAX = 2_147_483_647


class ClusterIn(Schema):
    """A cluster as it is registered: its writer, its PgBouncer (empty: its hubs are reached on its writer), whether
    new hubs may be placed on it, up to how many (0: no limit), and the prefix of its secrets (empty: the
    environment's roles)."""

    name: str = Field(min_length=1, max_length=63)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    pooler_host: str = Field(default="", max_length=255)
    pooler_port: int = Field(default=6432, ge=1, le=65535)
    is_open: bool = True
    max_hubs: int = Field(default=0, ge=0, le=INTEGER_MAX)
    secret_name: str = Field(default="", max_length=255)

    @field_validator("name", "host", "pooler_host", "secret_name", mode="before")
    @classmethod
    def _stripped(cls, value):
        return value.strip() if isinstance(value, str) else value


class ClusterUpdateIn(ClusterIn):
    """A cluster as it is edited: all of its fields, the ones that do not change included."""

    id: UUID


class ClusterIdIn(Schema):
    id: UUID


class ClusterOut(Schema):
    """A cluster with the number of hubs on it (a purged demo's is not counted: it has no database left)."""

    id: UUID
    name: str
    host: str
    port: int
    pooler_host: str
    pooler_port: int
    is_open: bool
    max_hubs: int
    secret_name: str
    hubs: int


class ClusterDeletedOut(Schema):
    id: UUID


class ClusterSizesIn(Schema):
    """Whose databases to measure: a cluster's, or (none) the ones on the settings' own server."""

    cluster: UUID | None = None


class ClusterSizesOut(Schema):
    """Each own database of a hub on that server, by name, with its size in bytes; one that is not there is absent."""

    databases: dict[str, int]
