"""The Home's health row (``base.health.list``); its rules are ``base.home_health``'s."""

from django.utils import translation
from live.context import OperationContext
from live.operations import INTERNAL, operation

from base import home, home_health
from base.apps_on import active_apps
from base.models import Hub
from base.permissions import VIEW_HOME
from base.schemas.health import HealthListIn, HealthListOut


# Not an assistant tool: the Home's own row; each app's state is asked of its own query (Printing's, the assistant's too).
@operation(
    "base.health.list",
    kind="query",
    permission=VIEW_HOME,
    input=HealthListIn,
    output=HealthListOut,
    ai=INTERNAL,
)
def health_list(ctx: OperationContext, data: HealthListIn) -> dict:
    """What the apps on say of their own (Printing: whether its receipt station answers now), for who runs the business:
    empty for everybody else, so the Home asks it for everybody."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        configs = home.shown_modules.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        return {"items": home_health.health_items(ctx, configs)}
