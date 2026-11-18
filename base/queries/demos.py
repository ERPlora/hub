"""A demo's status, for the platform (``base.demo.get``)."""

from typing import Any

from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import NotFound
from live.operations import INTERNAL, operation

from base.models import Hub
from base.registry import internal_only
from base.schemas.demos import DemoSlugIn, DemoStatusOut


# Not an assistant tool: the SaaS's door to the demo (/internal), no person.
@operation("base.demo.get", kind="query", permission=None, input=DemoSlugIn, output=DemoStatusOut, ai=INTERNAL)
def demo_get(ctx: OperationContext, data: DemoSlugIn) -> dict[str, Any]:
    """The status of the demo ``data.slug``, for the platform only: ``manage.py demo_expire`` says it once done."""
    internal_only(ctx)
    hub = Hub.objects.filter(slug=data.slug, is_demo=True).first()
    if hub is None:
        raise NotFound(gettext("No demo has this address."))
    return {"slug": hub.slug, "status": hub.status, "expires_at": hub.expires_at}
