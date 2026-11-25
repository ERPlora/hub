"""Where a business buys on erplora.com: its plans and its Store's apps.

ERPlora's own hub is nobody's customer, so it gets no address: where none comes, nothing that sells is offered
(``frontend/lib/plan-link.ts``). Nor does a server that is not linked to erplora.com.
"""

from uuid import UUID

from django.conf import settings

from base import platform_hub
from base.auth import SAAS_PANEL_PATH, saas_url


def plans_url(slug: str, business: UUID | None = None) -> str:
    """The plans for the hub of ``slug``, those of its business when ``business`` (its id) is given; empty when it buys
    nothing."""
    return _store_url("plans", slug, business)


def apps_url(slug: str, business: UUID) -> str:
    """The Store's paid apps for the hub of ``slug``; empty when it buys nothing."""
    return _store_url("modules", slug, business)


def _store_url(page: str, slug: str, business: UUID | None) -> str:
    if not settings.SAAS_URL or platform_hub.is_platform_slug(slug):
        return ""
    named = f"?business={business}" if business is not None else ""
    return saas_url(f"{SAAS_PANEL_PATH}/store/{page}{named}")
