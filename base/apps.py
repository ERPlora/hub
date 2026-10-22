"""The platform app of hub-next (Odoo's ``base``): session, permissions and the SPA.

A LiveAppConfig of kind "platform" (round 15, PLAN §20): always on, never turned on or off by a
hub, so it declares no module fields (no requires, category, premium or menu of its own).
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class BaseConfig(LiveAppConfig):
    name = "base"
    label = "base"
    kind = "platform"
    verbose_name = _("Base")
    default_auto_field = "django.db.models.BigAutoField"
    # The Home (PLAN-HUB round 2026-10-21): everyone of the hub sees it; whoever runs the hub (the old hub's
    # ``hub.administer``) is told its platform steps and the failed events.
    permissions = ["base.view_home", "base.administer_hub"]
    role_permissions = {
        "hub_owner": ["base.*"],
        "hub_admin": ["base.*"],
        "hub_manager": ["base.view_home"],
        "hub_employee": ["base.view_home"],
    }

    def ready(self) -> None:
        # Importing the scheduler registers the check of the apps' scheduled tasks (tag "base").
        from base import scheduler  # noqa: F401
