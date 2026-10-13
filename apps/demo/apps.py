"""The demo app: the reference every app of hub-next copies (plan §4.5)."""

from django.utils.translation import gettext_lazy as _
from live.meta import Category, LiveAppConfig, Nav


class DemoConfig(LiveAppConfig):
    name = "apps.demo"
    label = "demo"
    kind = "app"
    verbose_name = _("Demo")
    icon = "ion:flask-outline"
    category = Category.ORGANIZATION
    premium = False
    default_auto_field = "django.db.models.BigAutoField"
    permissions = ["demo.view", "demo.manage"]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included).
    role_permissions = {
        "hub_owner": ["demo.*"],
        "hub_admin": ["demo.*"],
        "hub_manager": ["demo.*"],
        "hub_employee": ["demo.view"],
    }
    navigation = [Nav(id="demo", label=_("Demo"), icon="ion:flask-outline", path="/demo/items")]
