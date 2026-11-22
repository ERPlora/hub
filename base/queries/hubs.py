"""The registry's row of a hub for the platform (``base.hub.get``, ``base.hub.by_slugs``), the business's settings
(``base.business.get``) and its locations (``base.location.list``)."""

from typing import Any

from django.conf import settings
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound
from live.operations import AI, INTERNAL, operation

from base import business
from base.auth import SAAS_PANEL_PATH, saas_url
from base.models import Hub
from base.models.locations import Location
from base.operations import is_platform_hub
from base.permissions import VIEW_HOME
from base.registry import hub_answer, internal_only
from base.schemas.business import BusinessIn, BusinessOut, LocationListIn, LocationListOut
from base.schemas.hub_registry import HubGetIn, HubGetOut, HubsBySlugIn, HubsBySlugOut


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.hub.get", kind="query", permission=None, input=HubGetIn, output=HubGetOut, ai=INTERNAL)
def hub_get(ctx: OperationContext, data: HubGetIn) -> dict[str, Any]:
    """The registry's row of ``data.id`` and control's active freeze, for the SaaS's signed status poll.

    Maintenance is global provisioning state, not part of the SaaS photo: reading it never changes ``state_version``;
    a repeated poll is idempotent and one after a missed notification or a lift recovers the current truth.
    """
    from control.queries import active_freeze

    internal_only(ctx)
    hub = Hub.objects.filter(pk=data.id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    freeze = active_freeze()
    maintenance = None if freeze is None else {"frozen": freeze.frozen, "reason": freeze.reason, "since": freeze.since}
    return {**hub_answer(hub), "maintenance": maintenance}


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.hub.by_slugs", kind="query", permission=None, input=HubsBySlugIn, output=HubsBySlugOut, ai=INTERNAL)
def hubs_by_slugs(ctx: OperationContext, data: HubsBySlugIn) -> dict[str, Any]:
    """The registry's status of each of ``data.slugs`` (``None`` without a row), in their order, for the platform
    only: ``seed_local_hubs --check`` asks it about ``a`` and ``b``."""
    internal_only(ctx)
    found = dict(Hub.objects.filter(slug__in=data.slugs).values_list("slug", "status"))
    return {"hubs": [{"slug": slug, "status": found.get(slug)} for slug in data.slugs]}


# ── Business settings and the hub's context ───────────────


@operation(
    "base.business.get",
    kind="query",
    permission=VIEW_HOME,
    input=BusinessIn,
    output=BusinessOut,
    ai=AI(
        description=(
            "Reads this business's name, country, time zone, language and currency, as erplora.com registered it. They "
            "are changed on erplora.com by the owner or an administrator, never here; the country no longer changes "
            "once the business is ready, and the currency is always the country's."
        ),
        asks={
            "en": (
                "what currency is the business in?",
                "what's our time zone?",
                "under what name is the business registered?",
            ),
            "es": (
                "¿en qué moneda trabaja el negocio?",
                "¿qué zona horaria tenemos?",
                "¿con qué nombre está dado de alta el negocio?",
            ),
        },
    ),
)
def business_get(ctx: OperationContext, data: BusinessIn) -> dict:
    """Settings › Business and what the old ``/api/hub/context`` gave: the business as the
    SaaS registered it, from the registry of this scope, never another's. The currency is its country's
    (``base.business``); a demo has no business on erplora.com, hence no address to change it, and the deployment's
    zone and language until the SaaS says otherwise. ERPlora's own hub is ERPlora itself, the issuer of
    its invoices: its legal name and country from ``PLATFORM_ISSUER_*``, row or not (``create_platform_hub`` makes
    it), so its currency is the one its invoices and its apps charge in; nothing of it is changed
    on erplora.com. Every app asks for that currency through ``base.operations.business_currency``."""
    if is_platform_hub(ctx.scope):
        return _business(
            ctx,
            name=settings.PLATFORM_ISSUER_LEGAL_NAME,
            country=settings.PLATFORM_ISSUER_COUNTRY,
            zone=settings.TIME_ZONE,
            language=settings.LANGUAGE_CODE,
            demo=False,
            settings_url="",
        )
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    if hub is None:
        raise NotFound(gettext("There is no business here."))
    return _business(
        ctx,
        name=hub.name,
        country=hub.country,
        zone=business.zone_name(business.zone_of(hub.timezone)),
        language=hub.language or settings.LANGUAGE_CODE,
        demo=hub.is_demo,
        settings_url="" if hub.is_demo else saas_url(f"{SAAS_PANEL_PATH}/businesses/{hub.id}/settings"),
    )


def _business(  # noqa: PLR0913
    ctx: OperationContext, *, name: str, country: str, zone: str, language: str, demo: bool, settings_url: str
) -> dict:
    """``BusinessOut`` of one business, each value named in ``ctx``'s language."""
    currency = business.currency_of(country)
    return {
        "name": name,
        "country": country,
        "country_name": business.country_name(country, ctx.language),
        "timezone": zone,
        "language": language,
        "language_name": business.language_name(language, ctx.language),
        "currency": currency,
        "currency_label": business.currency_label(currency, ctx.language),
        "currency_decimals": business.currency_decimals(currency),
        "demo": demo,
        "settings_url": settings_url,
    }


# ── Locations ──────────────────────────────────────────────────────────────────────────────────────────────────────


@operation(
    "base.location.list",
    kind="query",
    permission=VIEW_HOME,
    input=LocationListIn,
    output=LocationListOut,
    ai=AI(
        description=(
            "Lists the places this business works in (its shops, bars or salons), the default one first, and whether "
            "each is still in use. A business with one place has only its default one."
        ),
        asks={
            "en": ("which shops do we have?", "list our locations", "which is our main salon?"),
            "es": ("¿qué locales tenemos?", "¿cuáles son nuestras tiendas?", "¿cuál es el local principal?"),
        },
    ),
)
def location_list(ctx: OperationContext, data: LocationListIn) -> dict:
    """The business's locations, for everyone of the hub: the default first, then by name, those no longer in use
    too."""
    rows = Location.objects.order_by("-is_default", "name", "id")
    return {
        "locations": [
            {"id": row.id, "name": row.display_name, "is_default": row.is_default, "is_active": row.is_active}
            for row in rows
        ]
    }
