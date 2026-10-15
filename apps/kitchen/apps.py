"""The kitchen app: the kitchen display — the rounds the till fires, their dishes per station, the
pass, and the kitchen's history (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import Category, LiveAppConfig, Nav


class KitchenConfig(LiveAppConfig):
    name = "apps.kitchen"
    label = "kitchen"
    kind = "app"
    verbose_name = _("Kitchen")
    # Registered in the shell (ION_ICONS); the old `restaurant-outline` waits in UI-REQUESTS.md.
    icon = "ion:ticket-outline"
    category = Category.RESTAURANT
    premium = False
    # The public store's texts (round 16, PLAN §21), which register_apps writes to shared.app.
    summary = _(
        "The kitchen display: every round the till sends, dish by dish, per station and to the pass."
    )
    description = _(
        "Kitchen turns every round the waiter sends from the till into a ticket on a kitchen display that "
        "reads from a metre away. Each dish goes to its station — grill, bar, desserts — on the screen and "
        "on paper; the cooks tap a dish when it is done and the ticket moves to the pass by itself when "
        "nothing is left to cook. Rush a round after it was sent, see how much is left to cook, get a "
        "sound when a ticket arrives, a green-amber-red clock on every card, and the history of what "
        "happened in the kitchen."
    )
    verticals = ["restaurant"]
    # A ticket is a round of a check of Sales (its lines, read with Sales' models); a dish goes to the
    # station of its product or its category of Inventory (foreign keys of the routing).
    requires = ["sale", "inventory"]
    default_auto_field = "django.db.models.BigAutoField"
    permissions = [
        "kitchen.view_ticket",
        "kitchen.add_ticket",
        "kitchen.change_ticket",
        "kitchen.complete_ticket",
        "kitchen.cancel_ticket",
        "kitchen.delete_ticket",
        "kitchen.manage_station",
        "kitchen.change_settings",
        "kitchen.view_log",
    ]
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The old cashier
    # and the cook are employees: they move states; the manager also cancels, deletes, runs the
    # stations and saves the settings.
    role_permissions = {
        "hub_owner": ["kitchen.*"],
        "hub_admin": ["kitchen.*"],
        "hub_manager": ["kitchen.*"],
        "hub_employee": [
            "kitchen.view_ticket",
            "kitchen.add_ticket",
            "kitchen.change_ticket",
            "kitchen.complete_ticket",
            "kitchen.view_log",
        ],
    }
    # Positional (id, label, icon, path). Registered icons only: the old `tv`, `clipboard-outline` and
    # `flame-outline` wait in UI-REQUESTS.md. The same icons as the tabbar (frontend/tabs.ts), which
    # adds Settings for whoever may save them, as the old shell did.
    navigation = [
        Nav("display", _("Display"), "ion:desktop-outline", "/kitchen/display"),
        Nav("tickets", _("Tickets"), "ion:list-outline", "/kitchen/tickets"),
        Nav("stations", _("Stations"), "ion:layers-outline", "/kitchen/stations"),
        Nav("history", pgettext_lazy("kitchen menu", "History"), "ion:time-outline", "/kitchen/history"),
    ]
