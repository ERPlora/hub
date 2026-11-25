"""The write: ``register_apps`` upserts the registry into the SaaS's ``shared`` schema, in one transaction."""

import logging
from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.db import DatabaseError, connections, transaction
from django.db.models import Max
from django.utils import timezone
from live.shared_catalog import DOC_LANGUAGES

from base.catalog.app_registry import AppEntry, build_registry
from base.catalog.errors import CatalogError, SharedSchemaNotReady
from base.catalog.workbooks import source_hash
from base.routers import SHARED_ALIAS
from shared.models import App, AppDoc

logger = logging.getLogger("base.catalog")  # logged as the catalog, whose write this is

#: What register_apps needs on each table of ``shared`` (``bootstrap_databases`` grants it to hub_shared).
_TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE")
#: Two workers of a deploy in progress never write at the same time (released with the transaction).
_REGISTER_LOCK = (
    "SELECT pg_advisory_xact_lock(hashtext('erplora.shared.register_apps'))"
)


@dataclass(frozen=True)
class Release:
    """The release that writes: the image's commit (``APP_VERSION``) and its time (``APP_RELEASED_AT``)."""

    version: str
    released_at: datetime


@dataclass(frozen=True)
class RegisterResult:
    written: int  # apps of the code, upserted
    retired: int  # apps no longer in the code, unlisted by this run
    docs_changed: int  # documents inserted or changed
    skipped: bool  # a newer release had already registered its apps: nothing written
    apps: tuple[str, ...] = ()  # the labels written


def release() -> Release:
    """This image's release. Production demands both settings; locally: ``dev``, written now.

    A release is ordered by its commit's time, not its sha (shas do not sort) nor the time of the
    write (an old release that started late would look newer).
    """
    version, released_at = settings.APP_VERSION, settings.APP_RELEASED_AT
    if not settings.DEBUG:
        missing = [
            name
            for name, value in (
                ("APP_VERSION", version),
                ("APP_RELEASED_AT", released_at),
            )
            if not value
        ]
        if missing:
            raise CatalogError(
                f"{' and '.join(missing)} not set: the image's build fixes them (--build-arg) and "
                "register_apps never guesses a release in production."
            )
    try:
        moment = datetime.fromisoformat(released_at) if released_at else timezone.now()
    except ValueError as error:
        raise CatalogError(
            f"APP_RELEASED_AT={released_at!r} is not ISO 8601: {error}."
        ) from error
    if timezone.is_naive(moment):
        raise CatalogError(
            f"APP_RELEASED_AT={released_at!r} has no UTC offset: use the commit's time in ISO 8601."
        )
    return Release(version or "dev", moment)


def register_apps(
    registry: list[AppEntry] | None = None, *, force: bool = False
) -> RegisterResult:
    """Write the registry (default: ``build_registry()``) into ``shared``, in one transaction.

    Never overwrites what a newer release registered unless ``force`` (a deliberate
    rollback), never deletes (a retired app is unlisted, a retired translation left empty) and
    leaves nothing written when anything fails: the error is logged and raised. Tables the SaaS has
    not created yet raise ``SharedSchemaNotReady`` without logging: the worker waits for them.
    """
    try:
        if SHARED_ALIAS not in settings.DATABASES:
            raise CatalogError(
                f"The {SHARED_ALIAS!r} database alias is not configured: register_apps needs "
                "SHARED_DB_USER and SHARED_DB_PASSWORD, which only the worker task has."
            )
        this = release()
        registry = build_registry() if registry is None else registry
        with transaction.atomic(using=SHARED_ALIAS):
            with connections[SHARED_ALIAS].cursor() as cursor:
                cursor.execute(_REGISTER_LOCK)
                _check_tables(cursor)
                _check_columns(cursor)
            newest = App.objects.using(SHARED_ALIAS).aggregate(
                newest=Max("registered_at")
            )["newest"]
            if newest is not None and newest > this.released_at and not force:
                logger.info(
                    "register_apps: a newer release (registered at %s) already registered its apps; "
                    "nothing written by %s (%s).",
                    newest.isoformat(),
                    this.version,
                    this.released_at.isoformat(),
                )
                return RegisterResult(
                    written=0, retired=0, docs_changed=0, skipped=True
                )
            _upsert_apps(registry, this)
            retired = _retire_missing(registry, this)
            docs_changed = _write_documents(registry)
    except SharedSchemaNotReady:
        # Not an error yet: the caller says how loud it is (the worker waits; the command fails).
        raise
    except (CatalogError, DatabaseError) as error:
        logger.error("register_apps: nothing written: %s", error)
        raise
    logger.info(
        "register_apps: %d apps written, %d retired, %d documents changed (release %s at %s).",
        len(registry),
        retired,
        docs_changed,
        this.version,
        this.released_at.isoformat(),
    )
    return RegisterResult(
        written=len(registry),
        retired=retired,
        docs_changed=docs_changed,
        skipped=False,
        apps=tuple(entry.id for entry in registry),
    )


def _schema_and_table(db_table: str) -> tuple[str, str]:
    """``("shared", "app")`` from the quoted ``'"shared"."app"'``."""
    schema, table = (part.strip('"') for part in db_table.split("."))
    return schema, table


def _check_tables(cursor) -> None:
    """Both tables of the mirror exist and this role may use them.

    Missing, the SaaS has not migrated ``shared`` yet: ``SharedSchemaNotReady``, which the worker
    waits for. Present without the grants of ``bootstrap_databases``: a fatal ``CatalogError``
    naming them. Read from ``pg_catalog``, which every role sees whatever its grants:
    ``information_schema`` hides a table the role has no privilege on, which would pass for «not
    migrated yet» (the worker waiting for ever) or for «no column».
    """
    tables = [_schema_and_table(model._meta.db_table) for model in (App, AppDoc)]
    cursor.execute(
        "SELECT n.nspname, c.relname, has_schema_privilege(n.oid, 'USAGE'), "
        + ", ".join(
            f"has_table_privilege(c.oid, '{privilege}')"
            for privilege in _TABLE_PRIVILEGES
        )
        + ", current_user FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
        "WHERE c.relkind IN ('r', 'p') AND n.nspname = ANY(%s) AND c.relname = ANY(%s)",
        [
            sorted({schema for schema, _ in tables}),
            sorted({table for _, table in tables}),
        ],
    )
    present = {(row[0], row[1]): row for row in cursor.fetchall()}
    missing = [
        f"{schema}.{table}" for schema, table in tables if (schema, table) not in present
    ]
    if missing:
        raise SharedSchemaNotReady(missing)
    lacking, role = [], ""
    for schema, table in tables:
        _, _, usage, *granted, role = present[schema, table]
        if not usage and f"USAGE on schema {schema}" not in lacking:
            lacking.append(f"USAGE on schema {schema}")
        absent = [
            privilege
            for privilege, has in zip(_TABLE_PRIVILEGES, granted, strict=True)
            if not has
        ]
        if absent:
            lacking.append(f"{', '.join(absent)} on {schema}.{table}")
    if lacking:
        raise CatalogError(
            f"role {role} lacks {'; '.join(lacking)}: run bootstrap_databases (it grants hub_shared "
            "USAGE on the schema and SELECT, INSERT and UPDATE on its tables, also those the SaaS's "
            "migration creates later)."
        )


def _check_columns(cursor) -> None:
    """Every column of the mirror exists in the database; one more there is no error."""
    tables = {model: _schema_and_table(model._meta.db_table) for model in (App, AppDoc)}
    cursor.execute(
        "SELECT table_schema, table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = ANY(%s) AND table_name = ANY(%s)",
        [
            sorted({schema for schema, _ in tables.values()}),
            sorted({table for _, table in tables.values()}),
        ],
    )
    present = {tuple(row) for row in cursor.fetchall()}
    missing = [
        f"{schema}.{table}.{column.column}"
        for model, (schema, table) in tables.items()
        for column in model._meta.concrete_fields
        if (schema, table, column.column) not in present
    ]
    if missing:
        raise CatalogError(
            f"the database has no column {', '.join(missing)}: migrate the SaaS first (its release that "
            "adds them goes before the Hub's that writes them)."
        )


def _upsert_apps(registry: list[AppEntry], this: Release) -> None:
    columns = [
        field.name for field in App._meta.concrete_fields if not field.primary_key
    ]
    App.objects.using(SHARED_ALIAS).bulk_create(
        [
            App(
                id=entry.id,
                name_en=entry.name_en,
                name_es=entry.name_es,
                summary_en=entry.summary_en,
                summary_es=entry.summary_es,
                description_en=entry.description_en,
                description_es=entry.description_es,
                icon=entry.icon,
                icon_svg=entry.icon_svg,
                category=entry.category,
                premium=entry.premium,
                requires=entry.requires,
                verticals=entry.verticals,
                listed=entry.listed,
                hub_version=this.version,
                registered_at=this.released_at,
            )
            for entry in registry
        ],
        update_conflicts=True,
        unique_fields=["id"],
        update_fields=columns,
    )


def _retire_missing(registry: list[AppEntry], this: Release) -> int:
    """Unlist the apps no longer in the code (never deleted); returns how many were listed."""
    gone = App.objects.using(SHARED_ALIAS).exclude(
        id__in=[entry.id for entry in registry]
    )
    retired = gone.filter(listed=True).count()
    gone.update(listed=False, hub_version=this.version, registered_at=this.released_at)
    return retired


def _write_documents(registry: list[AppEntry]) -> int:
    """Insert the new documents and change those whose hash changed; returns how many.

    A language that no longer exists (a deleted ``WORKBOOK.en.md``) is left with ``markdown = ""``,
    which the SaaS treats as absent: never a ``DELETE``.
    """
    docs = AppDoc.objects.using(SHARED_ALIAS)
    existing = {
        (doc.app_id, doc.lang): doc
        for doc in docs.filter(app_id__in=[entry.id for entry in registry])
    }
    now = timezone.now()
    created, changed = [], []
    for entry in registry:
        for lang in DOC_LANGUAGES:
            markdown = entry.docs.get(lang, "")
            digest = source_hash(markdown)
            doc = existing.get((entry.id, lang))
            if doc is None:
                if markdown:
                    created.append(
                        AppDoc(
                            app_id=entry.id,
                            lang=lang,
                            markdown=markdown,
                            source_hash=digest,
                            updated_at=now,
                        )
                    )
            elif doc.source_hash != digest:
                doc.markdown, doc.source_hash, doc.updated_at = markdown, digest, now
                changed.append(doc)
    docs.bulk_create(created)
    docs.bulk_update(changed, ["markdown", "source_hash", "updated_at"])
    return len(created) + len(changed)
