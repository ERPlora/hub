"""The Hub's platform app (Odoo's ``base``): session, permissions and the SPA.

A LiveAppConfig of kind "platform": always on, never turned on or off by a hub, so it declares no module fields (no
requires, category, premium or menu of its own).
"""

import re
from functools import cached_property

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.meta import LiveAppConfig, all_live_app_configs

#: Where an app is said to go, beside its name: out of the menu turns it off, into it or in it turns it on.
OUT_OF_THE_MENU = ("del menu", "from the menu", "out of the menu", "off the menu")
INTO_THE_MENU = (
    "al menu",
    "en el menu",
    "disponible en el menu",
    "to the menu",
    "in the menu",
    "on the menu",
    "back on the menu",
    "back in the menu",
    "back to the menu",
    "available in the menu",
    "available on the menu",
)
#: What joins the two names of one app («Ventas / TPV», «Menús y combos», «Sales & POS»): each is said alone.
_JOINED_NAMES = re.compile(r"\s*[/&]\s*|\s+(?:y|and)\s+")


def store_app_names() -> list[str]:
    """The names of the apps a business turns on or off, in every language of the Hub, lowercase."""
    found = set()
    for config in all_live_app_configs():
        if config.kind == "app" and config.listed:
            for language, _label in settings.LANGUAGES:
                with translation.override(language):
                    found.update(_JOINED_NAMES.split(str(config.verbose_name).lower()))
    return sorted(found)


def beside_names(names: list[str], places: tuple[str, ...]) -> tuple[str, ...]:
    """Each place said after each name and before it («Tareas del menú», «del menú Tareas»)."""
    return tuple(phrase for name in names for place in places for phrase in (f"{name} {place}", f"{place} {name}"))


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
    # The four data permissions (base.sensitive) say which sensitive data a role sees: a manager sees them all, an
    # employee only the customers' contact details, which serving them needs.
    # Owning the business is the owner's alone (base.permissions.OWNER_ONLY): no role but the owner gets it.
    permissions = {
        "base.view_home": _("View the Home and its panels"),
        "base.administer_hub": _("Run the business: apps, settings, people and devices"),
        "base.view_files": _("View and open the files"),
        "base.upload_files": _("Upload and rename files"),
        "base.delete_files": _("Delete files"),
        "base.open_management": _("Open this business on erplora.com"),
        "base.view_costs": _("View costs"),
        "base.view_customer_contact": _("View customer contact details"),
        "base.view_team_contact": _("View team contact details"),
        "base.view_business_totals": _("View business totals"),
        "base.own_business": _("Reset the business, download its backups and upgrade the plan"),
    }
    role_permissions = {
        "hub_owner": ["base.*"],
        "hub_admin": ["base.*"],
        "hub_manager": [
            "base.view_home",
            "base.view_files",
            "base.open_management",
            "base.view_costs",
            "base.view_customer_contact",
            "base.view_team_contact",
            "base.view_business_totals",
        ],
        "hub_employee": ["base.view_home", "base.view_files", "base.view_customer_contact"],
        "hub_accountant": ["base.view_home", "base.view_business_totals"],
    }

    @cached_property
    def assistant_synonyms(self) -> tuple[tuple[str, ...], ...]:
        """What base's words mean to the Hub's assistant (``base.assistant.relevance.synonyms``): an app's name said
        with the menu («quita Tareas del menú», «put Tasks back on the menu») is the app, turned off or on. Only beside
        a name: «los postres del menú vegano» is a menu of Menus and combos."""
        names = store_app_names()
        return (
            ("app", *beside_names(names, OUT_OF_THE_MENU + INTO_THE_MENU)),
            ("disable", *beside_names(names, OUT_OF_THE_MENU)),
            ("enable", *beside_names(names, INTO_THE_MENU)),
        )

    def ready(self) -> None:
        # Importing the scheduler registers the check of the apps' scheduled tasks (tag "base"), the print channel the
        # one of the print hosts' presence (base.E006), the Home the one of the bell's clock (base.E007), its health row
        # the one of the apps' health (base.E021), the file server the one of the folders the apps declare (base.E010)
        # and the relay the one of the actors they declare passed on (base.E017).
        from base import home, home_health, media, relay, scheduler, ws_print  # noqa: F401
        from base.tenancy import deletion

        deletion.install()
