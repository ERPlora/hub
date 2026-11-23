"""The business's API keys (``base.api_key.*``) and their check at the API's door, and the API's documentation
(``base.api_doc.settings_update``).
"""

import datetime as dt
from uuid import UUID

from django.db import IntegrityError
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError, PermissionDenied
from live.operations import AI, atomic, operation
from live.outbox import record_event

from base import api_keys, events, queries
from base.models.api_keys import ApiKey, ApiSettings
from base.permissions import ADMINISTER_HUB
from base.sensitive import DATA_PERMISSIONS
from base.schemas.api_keys import (
    ApiDocSettingsIn,
    ApiDocSettingsOut,
    ApiDocSettingsUpdateIn,
    ApiKeyCreateIn,
    ApiKeyIdIn,
    ApiKeyRevokeOut,
    ApiKeyTokenOut,
)
from base.services.devices import _actor_label, too_many_message
from base.throttle import client_key


def _checked_scopes(ctx: OperationContext, data: ApiKeyCreateIn) -> dict:
    """What a key per app may do on each app, of those this business has that publish it; nothing for the others."""
    if data.mode != ApiKey.Mode.PER_APP:
        return {}
    offered = {app["id"]: app for app in queries.api_keys.api_apps(ctx)}
    scopes = {app: sorted(set(kinds)) for app, kinds in data.scopes.items() if kinds}
    if not scopes:
        message = gettext("Choose at least one app and what the key may do on it.")
        raise InvalidPayload(message, code="base.api_key_scopes_required", fields={"scopes": message})
    for app, kinds in scopes.items():
        found = offered.get(app)
        if found is None or any(not found[kind] for kind in kinds):
            message = gettext("That app does not publish what the key would do on it.")
            raise InvalidPayload(message, code="base.api_key_scope_unknown", fields={"scopes": message})
    return scopes


def _new_token_for(key: ApiKey) -> str:
    token = api_keys.new_token()
    key.token_digest, key.prefix = api_keys.digest(token), token[: api_keys.PREFIX_LENGTH]
    return token


@operation(
    "base.api_key.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ApiKeyCreateIn,
    output=ApiKeyTokenOut,
    ai={
        "description": "Not an assistant tool (its token is a secret shown once, never in a chat): makes an API key "
        "for another system, with a name, its requests a minute and what it may do.",
        "risk": "high",
    },
)
def api_key_create(ctx: OperationContext, data: ApiKeyCreateIn) -> dict:
    """«New API key»: its token once; the hub keeps its digest and its first characters."""
    name = " ".join(data.name.split())
    if not name:
        message = gettext("Give the key a name.")
        raise InvalidPayload(message, code="base.api_key_name_required", fields={"name": message})
    key = ApiKey(
        name=name,
        mode=data.mode,
        scopes=_checked_scopes(ctx, data),
        rate_per_minute=data.rate_per_minute,
        created_by=_actor_label(ctx),
    )
    token = _new_token_for(key)
    key.save()
    record_event(ctx, events.API_KEY_CREATED, {"id": str(key.id), "mode": key.mode})
    return {"key": queries.api_keys.api_key_out(key), "token": token}


def _live_key(key_id: UUID) -> ApiKey:
    key = ApiKey.objects.select_for_update().filter(pk=key_id).first()
    if key is None:
        raise NotFound(gettext("That key no longer exists. Refresh the list and try again."), code="base.api_key_not_found")
    if key.revoked_at is not None:
        raise Conflict(gettext("That key was revoked: it never works again."), code="base.api_key_revoked")
    return key


@operation(
    "base.api_key.rotate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ApiKeyIdIn,
    output=ApiKeyTokenOut,
    ai={
        "description": "Not an assistant tool (its new token is a secret shown once): gives an API key a new token; "
        "the old one stops working at once.",
        "risk": "high",
    },
)
def api_key_rotate(ctx: OperationContext, data: ApiKeyIdIn) -> dict:
    """«Rotate»: a new token, shown once; the old one stops at once (its digest is gone)."""
    key = _live_key(data.id)
    token = _new_token_for(key)
    key.rotated_at = timezone.now()
    key.save(update_fields=["token_digest", "prefix", "rotated_at"])
    record_event(ctx, events.API_KEY_ROTATED, {"id": str(key.id)})
    return {"key": queries.api_keys.api_key_out(key), "token": token}


@operation(
    "base.api_key.revoke",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ApiKeyIdIn,
    output=ApiKeyRevokeOut,
    ai=AI(
        description=(
            "Revokes an API key: any system using it loses access at once, for good. The key stays listed as revoked."
        ),
        risk="high",
        asks={
            "en": (
                "revoke the old Shopify key",
                "cut off the key the accountant was using",
                "kill that API key, it leaked",
            ),
            "es": (
                "revoca la clave de la tienda online",
                "córtale el acceso a la clave de la gestoría",
                "anula esa clave de API, se ha filtrado",
            ),
        },
    ),
)
def api_key_revoke(ctx: OperationContext, data: ApiKeyIdIn) -> dict:
    """«Revoke»: at once and for good; the key is kept, for the record."""
    key = _live_key(data.id)
    key.revoked_at, key.revoked_by = timezone.now(), _actor_label(ctx)
    key.save(update_fields=["revoked_at", "revoked_by"])
    record_event(ctx, events.API_KEY_REVOKED, {"id": str(key.id)})
    return {"key": queries.api_keys.api_key_out(key)}


#: A key's last use is written at most once a minute: a busy integration does not write on every call.
API_KEY_LAST_USE_EVERY = dt.timedelta(minutes=1)


def authenticate_api_key(request: HttpRequest, token: str, op) -> "api_keys.KeyCaller | None":
    """The caller of ``token`` on the published operation ``op``, in the request's hub (``base.api_keys.KeyDoor``).

    ``None`` (the session's door goes on) without a hub, or for a token nobody issued here (counted against the
    address); 429 once the address tried too many, or the key passed its pace; 403 when the key may not do this on this
    app."""
    hub = getattr(request, "hub", None)
    if hub is None:
        return None
    address = client_key(request)
    wait = api_keys.KEY_ADDRESS_LIMIT.wait(hub.slug, address)
    if wait:
        raise OperationError(
            too_many_message(wait, gettext("Too many keys tried from here.")),
            code="base.too_many_api_key_tries",
            status=429,
        )
    key = ApiKey.objects.filter(token_digest=api_keys.digest(token), revoked_at=None).first()
    if key is None:
        api_keys.KEY_ADDRESS_LIMIT.failed(hub.slug, address)
        return None
    if not api_keys.allows(key.mode, key.scopes, op.app_label, api_keys.kind_of(op)):
        raise PermissionDenied(
            gettext("This API key may not do that on this app."), code="base.api_key_scope"
        )
    if api_keys.over_pace(key.pk, key.rate_per_minute):
        raise OperationError(
            gettext("This API key went past its requests a minute: wait a moment."),
            code="base.api_key_rate_limited",
            status=429,
        )
    now = timezone.now()
    if key.last_used_at is None or now - key.last_used_at >= API_KEY_LAST_USE_EVERY:
        ApiKey.objects.filter(pk=key.pk).update(last_used_at=now)
    granted = (frozenset({op.permission}) if op.permission else frozenset()) | DATA_PERMISSIONS
    return api_keys.KeyCaller(key_id=str(key.pk), name=key.name, prefix=key.prefix, permissions=granted)


@operation(
    "base.api_doc.settings_update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=ApiDocSettingsUpdateIn,
    output=ApiDocSettingsOut,
    ai=AI(
        description=(
            "Shows or hides the documentation of this business's API (for whoever connects another system); it comes "
            "hidden."
        ),
        asks={
            "en": ("show the API docs to our developer", "hide the API documentation again"),
            "es": ("publica la documentación de la API para el programador", "oculta otra vez la doc de la API"),
        },
    ),
)
def api_doc_settings_update(ctx: OperationContext, data: ApiDocSettingsUpdateIn) -> dict:
    """«Show the API documentation»: saved at once."""
    row = ApiSettings.objects.select_for_update().first()
    if row is None:
        try:
            with atomic():
                row = ApiSettings.objects.create()
        except IntegrityError:
            row = ApiSettings.objects.select_for_update().get()
    row.docs_enabled = data.docs_enabled
    row.updated_by = _actor_label(ctx)
    row.save()
    record_event(ctx, events.API_DOC_SETTINGS_CHANGED, {"docs_enabled": data.docs_enabled})
    return queries.api_keys.api_doc_settings(ctx, ApiDocSettingsIn())
