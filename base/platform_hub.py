"""ERPlora's own hub by its name: the business that issues ERPlora's invoices (``create_platform_hub``).

It goes by ``PLATFORM_HUB_SLUG``; ``PLATFORM_HUB_FORMER_SLUG`` is the name its row had before, and keeps until
``create_platform_hub --rename``. Both are reserved (``live.slugs``), so no business bears either and a scope under one
or the other is ERPlora's own hub; only the name it goes by is served on a host.
"""

from typing import Any

from django.conf import settings
from live.slugs import validate_hub_slug


def names() -> tuple[str, str]:
    return settings.PLATFORM_HUB_SLUG, settings.PLATFORM_HUB_FORMER_SLUG


def is_platform_slug(slug: str) -> bool:
    return slug in names()


def validate_served_slug(slug: str, *, allow_demo: bool = False) -> str:
    """``slug`` if a hub may be served or opened in the admin under it: a business's (``live.slugs``) or, the one reserved
    name that is, the one ERPlora's own hub goes by; else ``ValueError`` with ``live.slugs``' code."""
    if slug == settings.PLATFORM_HUB_SLUG:
        return slug
    return validate_hub_slug(slug, allow_demo=allow_demo)


def may_be_served(hub: Any) -> bool:
    """Whether the registry's row ``hub`` is served under its name: under ERPlora's own hub's, only ERPlora's own row."""
    return hub.is_platform or hub.slug != settings.PLATFORM_HUB_SLUG
