"""The business's API keys (``base.api_key.*``) and the API's documentation (``base.api_doc.*``)."""

from collections import defaultdict
from typing import Any

from django.utils import translation
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.meta import module_configs
from live.operations import AI, operation, registry as operation_registry

from base import activation, api_actions, api_docs, entitlement
from base.models.api_keys import ApiKey, ApiSettings
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

from .people import without_address


# ── People and permissions: the business's API keys ────────────────────────────────────────────────────────────────


def api_key_out(key: ApiKey) -> dict[str, Any]:
    """A key as Employees › API keys shows it: never its token, only its first characters."""
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "scopes": api_actions.normalised(key.scopes),
        "rate_per_minute": key.rate_per_minute,
        "created_by": without_address(key.created_by),
        "created_at": key.created_at,
        "rotated_at": key.rotated_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
    }


def _reachable(ctx: OperationContext) -> dict[str, list]:
    """The published operations (``expose_api``) of each app a key reaches in this business, base's included: not
    blocked by its plan, not turned off."""
    blocked = entitlement.blocked_apps(ctx.scope) | activation.off_apps(ctx.scope)
    reachable: dict[str, list] = defaultdict(list)
    for op in operation_registry.values():
        if op.expose_api and op.app_label not in blocked:
            reachable[op.app_label].append(op)
    return reachable


def _actions(ops) -> list[str]:
    found = {api_actions.action_of(op) for op in ops}
    return [action for action in api_actions.ACTIONS if action in found]


def api_apps(ctx: OperationContext) -> list[dict[str, Any]]:
    """The modules this business has on that publish operations, each with what it publishes (read, create, update,
    delete), by name in who asks's language."""
    reachable = _reachable(ctx)
    with translation.override(ctx.language):
        apps = [
            {"id": config.label, "name": str(config.verbose_name), "actions": _actions(reachable[config.label])}
            for config in module_configs()
            if reachable.get(config.label)
        ]
    return sorted(apps, key=lambda app: app["name"].casefold())


def grantable(ctx: OperationContext) -> dict[str, list[str]]:
    """The most who asks may give a key, as a key's permissions: on each module, the actions they may do there (at
    least one of its operations of it: at each call the key is held to its maker's permission of that very operation);
    on ``"*"``, the actions they may do on every app that publishes them, base's included."""
    reachable = _reachable(ctx)
    published = {app: _actions(ops) for app, ops in reachable.items()}
    held = {app: _actions(op for op in ops if ctx.has(op.permission)) for app, ops in reachable.items()}
    everywhere = [
        action
        for action in api_actions.ACTIONS
        if any(action in actions for actions in published.values())
        and all(action in held[app] for app, actions in published.items() if action in actions)
    ]
    modules = {config.label for config in module_configs()}
    given = {app: actions for app, actions in held.items() if app in modules and actions}
    return {api_actions.EVERY_APP: everywhere, **given} if everywhere else given


@operation(
    "base.api_key.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApiKeyListIn,
    output=ApiKeyListOut,
    ai=AI(
        description=(
            "Lists this business's API keys for other systems: name, the start of the token (never the whole), what "
            "each may do (read, create, update or delete, on every app or app by app), its requests a minute, when it "
            "was last used and whether it was revoked; and the apps whose API a key can reach."
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
    """Employees › API keys: every key, the newest first, the apps a key may reach and the most who asks may give one."""
    keys = [api_key_out(key) for key in ApiKey.objects.all()]
    return {"keys": keys, "apps": api_apps(ctx), "grantable": grantable(ctx)}


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
