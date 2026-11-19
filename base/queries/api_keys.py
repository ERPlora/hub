"""The business's API keys (``base.api_key.*``) and the API's documentation (``base.api_doc.*``)."""

from typing import Any

from django.utils import translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.meta import module_configs
from live.operations import AI, operation, registry as operation_registry

from base import activation, api_docs, entitlement
from base.models import ApiKey, ApiSettings
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas.api_keys import (
    ApiDocIn,
    ApiDocOut,
    ApiDocSettingsIn,
    ApiDocSettingsOut,
    ApiKeyIdIn,
    ApiKeyListIn,
    ApiKeyListOut,
    ApiKeyOut,
)


# ── People and permissions: the business's API keys ────────────────────────────────────────────────────────────────


def api_key_out(key: ApiKey) -> dict[str, Any]:
    """A key as Employees › API keys shows it: never its token, only its first characters."""
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "mode": key.mode,
        "scopes": key.scopes if key.mode == ApiKey.Mode.PER_APP and isinstance(key.scopes, dict) else {},
        "rate_per_minute": key.rate_per_minute,
        "created_by": key.created_by,
        "created_at": key.created_at,
        "rotated_at": key.rotated_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
    }


def api_apps(ctx: OperationContext) -> list[dict[str, Any]]:
    """The modules this business has on (not blocked by its plan, not turned off) that publish operations
    (``expose_api``), each with whether it publishes queries (a key may read it) and commands (write), by name in who
    asks's language."""
    blocked = entitlement.blocked_apps(ctx.scope) | activation.off_apps(ctx.scope)
    published: dict[str, set[str]] = {}
    for op in operation_registry.values():
        if op.expose_api:
            published.setdefault(op.app_label, set()).add(op.kind)
    with translation.override(ctx.language):
        apps = [
            {"id": config.label, "name": str(config.verbose_name), "read": "query" in kinds, "write": "command" in kinds}
            for config in module_configs()
            if (kinds := published.get(config.label)) and config.label not in blocked
        ]
    return sorted(apps, key=lambda app: app["name"].casefold())


@operation(
    "base.api_key.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApiKeyListIn,
    output=ApiKeyListOut,
    ai=AI(
        description=(
            "Lists this business's API keys for other systems: name, the start of the token (never the whole), what "
            "each may do (all, read, write or per app), its requests a minute, when it was last used and whether it "
            "was revoked; and the apps whose API a key can reach."
        ),
        asks={
            "en": (
                "which API keys do we have?",
                "what systems are connected with a key?",
                "when was the Holded key last used?",
            ),
            "es": (
                "¿qué claves de API tenemos?",
                "¿qué programas están conectados con clave?",
                "¿cuándo se usó por última vez la clave de Holded?",
            ),
        },
    ),
)
def api_key_list(ctx: OperationContext, data: ApiKeyListIn) -> dict:
    """Employees › API keys: every key, the newest first, and the apps a key per app may reach."""
    return {"keys": [api_key_out(key) for key in ApiKey.objects.all()], "apps": api_apps(ctx)}


@operation(
    "base.api_key.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApiKeyIdIn,
    output=ApiKeyOut,
    ai=AI(
        description=(
            "Reads one API key of this business by its id, as the list of keys shows it: its name, the start of its "
            "token (never the whole), what it may do and whether it was revoked."
        ),
        asks={
            "en": ("what can the accountant's API key do?", "show me the Shopify key"),
            "es": ("¿qué permisos tiene la clave de la gestoría?", "dame los datos de la clave de Shopify"),
        },
    ),
)
def api_key_detail(ctx: OperationContext, data: ApiKeyIdIn) -> dict:
    """One key of Employees › API keys."""
    key = ApiKey.objects.filter(pk=data.id).first()
    if key is None:
        raise NotFound(gettext("That key no longer exists. Refresh the list and try again."))
    return api_key_out(key)


# ── People and permissions: the API's documentation ────────────────────────────────────────────────────────────────


def api_docs_enabled() -> bool:
    row = ApiSettings.objects.first()
    return bool(row is not None and row.docs_enabled)


@operation(
    "base.api_doc.settings",
    kind="query",
    permission=VIEW_HOME,
    input=ApiDocSettingsIn,
    output=ApiDocSettingsOut,
    ai=AI(
        description=(
            "Says whether this business shows the documentation of its API, and whether who asks may change it."
        ),
        asks={
            "en": ("is our API documentation visible?", "can the developer see the API docs?"),
            "es": ("¿está publicada la documentación de la API?", "¿el programador puede ver la doc de la API?"),
        },
    ),
)
def api_doc_settings(ctx: OperationContext, data: ApiDocSettingsIn) -> dict:
    """«Show the API documentation» in Settings › General; off without a row."""
    return {"docs_enabled": api_docs_enabled(), "can_change": ctx.has(ADMINISTER_HUB)}


@operation(
    "base.api_doc.get",
    kind="query",
    permission=VIEW_HOME,
    input=ApiDocIn,
    output=ApiDocOut,
    ai={
        "description": "Not an assistant tool (a long technical document): the OpenAPI document of the API this "
        "business's apps publish for other systems, when the business shows it."
    },
)
def api_doc_get(ctx: OperationContext, data: ApiDocIn) -> dict:
    """The API's documentation: what the apps this business has publish; not given while hidden."""
    if not api_docs_enabled():
        raise Conflict(gettext("The API documentation is hidden in this business."), code="base.api_docs_hidden")
    apps = api_apps(ctx)
    return {"document": api_docs.public_document({app["id"] for app in apps}), "apps": apps}
