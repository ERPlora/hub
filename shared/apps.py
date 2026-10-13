"""The mirror of the SaaS's ``shared`` schema (round 16, PLAN §21; spec §3.2).

A platform app at the root, next to ``base/``: always installed, only ``models.py`` (no routes, no
migrations). Its models live on the ``shared`` database alias (``base.routers.SharedRouter``) and
only ``base/catalog.py`` uses them, to register the Hub's modules in the SaaS.
"""

from live.meta import LiveAppConfig


class SharedConfig(LiveAppConfig):
    name = "shared"
    label = "shared"
    kind = "platform"
    default_auto_field = "django.db.models.BigAutoField"
