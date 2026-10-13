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
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _("Items with lines that show up on every tablet at once: the platform's reference app.")
    description = _(
        "Demo keeps items with a name, a status and a note, each with its own list of lines. It solves "
        "no business problem: it proves on the tablet that the platform works end to end, with every "
        "change shown live on the other screens, lines added instantly and permissions enforced. It is "
        "the app every other app is copied from."
    )
    verticals = []
    # The technical reference, not sold (its WORKBOOK): registered, but kept out of the public store.
    listed = False
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
