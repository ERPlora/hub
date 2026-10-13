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
