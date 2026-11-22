"""The copies of the business's data (``base.hub.dumps``, ``base.hub.dump_link``, ``base.hub.dump_list``) and its last
reset."""

from django.utils import timezone, translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound, OperationError
from live.operations import AI, INTERNAL, operation

from base import blueprint
from base.models import Hub
from base.permissions import OWN_BUSINESS
from base.registry import internal_only
from base.schemas.dumps import HubDumpLinkIn, HubDumpLinkOut, HubDumpsIn, HubDumpsOut, InternalDumpsOut
from base.schemas.hub_registry import HubGetIn
from control.models import HubDump


# ── The copies of the business's data ─────────────────────────────────────────────────────────────────────────────


def _dumps_unavailable() -> OperationError:
    return OperationError(
        gettext("The copy cannot be downloaded right now. Try again in a moment."),
        code="base.dumps_unavailable",
        status=503,
    )


def _reset_state(hub: Hub) -> dict | None:
    """The last reset of ``hub`` as Settings › Data shows it (``Hub.reset_sections``), or ``None`` before the first."""
    asked = hub.reset_sections if isinstance(hub.reset_sections, dict) else None
    if not asked or asked.get("state") not in ("copying", "emptying", "done", "failed"):
        return None
    return {
        "state": asked["state"],
        "sections": [{"id": app, "label": blueprint.datasets.app_label(app)} for app in asked.get("apps") or []],
        "requested_by": asked.get("requested_by") or "",
        "error": asked.get("error") or "",
        "removed": asked.get("removed") or [],
        "finished_at": asked.get("finished_at"),
    }


def _kept_dumps(hub: Hub):
    """The copies of ``hub`` still in the bucket, newest first: none past its 90 days (``dumps.RETENTION``), which the
    bucket's lifecycle rule deleted or is about to."""
    from base.tenancy import dumps

    return HubDump.objects.filter(hub=hub, created_at__gt=timezone.now() - dumps.RETENTION).order_by("-created_at", "-id")


def gets_copies(hub: Hub) -> bool:
    """Whether ``hub`` has, or will have, copies of its data: its own database, made (or being made); never a business
    that shares control's, nor one that left before its database was finished."""
    from base import registry

    return bool(hub.db_name) and (hub.ready_at is not None or hub.status in registry.PREPARING_STATUSES)


@operation(
    "base.hub.dumps",
    kind="query",
    permission=OWN_BUSINESS,
    input=HubDumpsIn,
    output=HubDumpsOut,
    ai=AI(
        description=(
            "Lists the full copies of this business's data that ERPlora keeps for 90 days (one before each reset, one "
            "when the business is deleted): when each was made and how big it is, newest first; and how the last "
            "reset of the business went (copying, emptying, done or failed, and what was removed)."
        ),
        asks={
            "en": ("do I have a backup of my data?", "show me the copies of my data made before the reset"),
            "es": ("¿tengo una copia de seguridad de mis datos?", "¿cómo fue el restablecimiento del negocio?"),
        },
    ),
)
def hub_dumps(ctx: OperationContext, data: HubDumpsIn) -> dict:
    """Settings › Data's «Copies»: the copies of the business's own database, without their links
    (``base.hub.dump_link`` gives one on each click), and how its last reset went (``base.services``, «The reset of a
    business»)."""
    with translation.override(ctx.language):
        hub = Hub.objects.get(slug=ctx.scope.key)
        return {
            "reset": _reset_state(hub),
            "dumps": [
                {"id": dump.pk, "kind": dump.kind, "created_at": dump.created_at, "bytes": dump.bytes}
                for dump in _kept_dumps(hub)
            ],
        }


# Not an assistant tool: a link that downloads every person's data of the business is for the person on the screen.
@operation(
    "base.hub.dump_link",
    kind="query",
    permission=OWN_BUSINESS,
    input=HubDumpLinkIn,
    output=HubDumpLinkOut,
    ai=INTERNAL,
)
def hub_dump_link(ctx: OperationContext, data: HubDumpLinkIn) -> dict:
    """The link of one copy of the business's data, signed for 15 minutes when it is asked (each «Download»); a copy of
    another business is not found."""
    from base.tenancy import dumps

    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        dump = _kept_dumps(hub).filter(pk=data.id).first() if hub is not None else None
        if dump is None:
            raise NotFound(gettext("This copy is no longer kept."))
        try:
            url = dumps.presigned_url(dump.key, filename=dumps.file_name(hub.slug, dump.key))
        except dumps.DumpsUnavailable:
            raise _dumps_unavailable() from None
        return {"url": url, "expires_at": dumps.link_expires_at(url)}


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation(
    "base.hub.dump_list", kind="query", permission=None, input=HubGetIn, output=InternalDumpsOut, ai=INTERNAL
)
def hub_dump_list(ctx: OperationContext, data: HubGetIn) -> dict:
    """The copies of ``data.id``'s data (``GET /internal/hubs/{id}/dumps``, the SaaS's panel and its mails of a
    deletion), newest first, each with a link of 15 minutes; ``available`` false for a business that never gets one.
    A business that left answers too (the 410 is its host's door); one unknown or purged is not found."""
    from base.tenancy import dumps

    internal_only(ctx)
    hub = Hub.objects.filter(pk=data.id).exclude(status=Hub.Status.PURGED).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    if not gets_copies(hub):
        return {"available": False, "dumps": []}
    if not dumps.configured():
        # No bucket: this Hub can make no copy, so «none yet» would promise one; it is a failure, not «none».
        raise _dumps_unavailable()
    rows = list(_kept_dumps(hub))
    try:
        listed = [
            {
                "id": dump.key,
                "kind": dump.kind,
                "created_at": dump.created_at,
                "bytes": dump.bytes,
                "url": dumps.presigned_url(dump.key, filename=dumps.file_name(hub.slug, dump.key)),
            }
            for dump in rows
        ]
    except dumps.DumpsUnavailable:
        raise _dumps_unavailable() from None
    return {"available": True, "dumps": listed}
