"""The Hub's platform app (Odoo's ``base``): session, permissions and the SPA.

A LiveAppConfig of kind "platform": always on, never turned on or off by a hub, so it declares no module fields (no
requires, category, premium or menu of its own).
"""

from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig


class BaseConfig(LiveAppConfig):
    name = "base"
    label = "base"
    kind = "platform"
    verbose_name = _("Base")
    default_auto_field = "django.db.models.BigAutoField"
    # Everyone of the hub sees the Home; whoever runs the hub is also told its platform steps and the failed events.
    # Everyone sees and opens the files; whoever runs the hub uploads, renames and deletes them.
    # «Manage on erplora.com» at the menu's foot: the owner, an administrator and a manager open this business on
    # erplora.com's panel; a manager does not administer the hub, so it is a permission of its own.
    permissions = [
        "base.view_home",
        "base.administer_hub",
        "base.view_files",
        "base.upload_files",
        "base.delete_files",
        "base.open_management",
    ]
    role_permissions = {
        "hub_owner": ["base.*"],
        "hub_admin": ["base.*"],
        "hub_manager": ["base.view_home", "base.view_files", "base.open_management"],
        "hub_employee": ["base.view_home", "base.view_files"],
    }

    def ready(self) -> None:
        # Importing the scheduler registers the check of the apps' scheduled tasks (tag "base"), the print channel the
        # one of the print hosts' presence (base.E006), the Home the one of the bell's clock (base.E007), the file
        # server the one of the folders the apps declare (base.E010) and the relay the one of the actors they declare
        # passed on (base.E017).
        from base import home, media, relay, scheduler, ws_print  # noqa: F401
        from base.tenancy import deletion

        deletion.install()
