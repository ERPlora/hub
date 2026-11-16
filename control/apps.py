"""The control database's app.

What the Hub keeps about its hubs, never inside any of them: the registry (``Hub``), the demos' codes, the clusters
and the hubs due for work. A platform app at the root, next to ``base/``: always installed, its
models in control's database only (``base.tenancy.router.TenantRouter``).
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class ControlConfig(LiveAppConfig):
    name = "control"
    label = "control"
    kind = "platform"
    verbose_name = _("Control")
    default_auto_field = "django.db.models.BigAutoField"
