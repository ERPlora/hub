"""The kitchen app: the kitchen display — the rounds the till fires, their dishes per station, the
pass, and the kitchen's history (WORKBOOK.md)."""

from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from live.meta import Category, DeviceNotice, Help, LiveAppConfig, Nav

#: A round is told as soon as Sales fires it; saving it or creating one by hand refreshes the same row.
NOTICE_EVENTS = ["kitchen.ticket.received", "kitchen.ticket.created", "sale.order.fired"]
NOTICE_BODY = ["{dish_names}", _("Waiter: {waiter}")]


class KitchenConfig(LiveAppConfig):
    name = "apps.kitchen"
    label = "kitchen"
    kind = "app"
    verbose_name = _("Kitchen")
    # Registered in the shell (ION_ICONS); `restaurant-outline` waits in UI-REQUESTS.md.
    icon = "ion:ticket-outline"
    category = Category.RESTAURANT
    premium = False
    # The public store's texts, which register_apps writes to shared.app.
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
    # What these words mean to the Hub's assistant (base.assistant.relevance.synonyms). The kitchen's ticket is its «comanda»
    # (kitchen.ticket, as its screens say): «la comanda», «qué comandas», «las comandas de…», named by its phrases and
    # never by the word, which live keeps for a table's order, and a «comandas» said in passing («sin alterar las
    # comandas ya enviadas») names no kitchen ticket. A kitchen's «estación», and its «puesto» named by its phrases («el
    # puesto», never «tenemos puesto…»), is its station (kitchen.station), what goes «urgente» or in a hurry («prisa») a
    # rush (kitchen.ticket.set_rush), the «enrutado» the routing (kitchen.routing), a dish marked «como listo» or «como
    # hecho» bumped (kitchen.item.bump) and one sent back «a pendientes» or «a preparación» recalled (kitchen.*.recall).
    assistant_synonyms = (
        (
            "ticket", "la comanda", "una comanda", "unas comandas", "esta comanda", "esa comanda", "su comanda",
            "sus comandas", "que comanda", "que comandas", "cuantas comandas", "otra comanda", "alguna comanda",
            "cada comanda", "comanda manual", "comandas manuales", "las comandas de",
        ),
        ("estacion", "estaciones", "station", "stations", "el puesto", "al puesto", "del puesto", "un puesto",
         "los puestos", "que puesto", "que puestos", "cada puesto", "por puesto"),
        ("urgente", "urgentes", "urgencia", "prisa", "rush", "urgent"),
        ("enrutado", "enrutados", "enrutar", "enruta", "enrutamiento", "routing", "route", "routes"),
        # the «regla» that sends a product or a family to a station is its routing (``kitchen.routing``): live reads
        # «regla» as any rule («rule», as Taxes' and Pricing's), and the QA says it of the routing.
        ("regla", "routing"),
        ("bump", "como listo", "como listos", "como lista", "como listas", "como hecho", "como hechos", "como hecha",
         "como hechas"),
        ("recall", "a pendientes", "a pendiente", "a preparacion", "a preparar"),
    )
    permissions = {
        "kitchen.view_ticket": _("View kitchen tickets, stations, routing and settings"),
        "kitchen.add_ticket": _("Send rounds and create tickets by hand"),
        "kitchen.change_ticket": _("Change tickets: fire, ready, recall, rush and reprint"),
        "kitchen.complete_ticket": _("Mark tickets served"),
        "kitchen.cancel_ticket": _("Cancel tickets"),
        "kitchen.delete_ticket": _("Delete tickets made by hand"),
        "kitchen.manage_station": _("Manage stations and routing"),
        "kitchen.change_settings": _("Change the settings"),
        "kitchen.view_log": _("View the history"),
    }
    # Keys are the customer roles as the SaaS sends them (``hub_`` prefix included). The cashier
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
    # Positional (id, label, icon, path). Registered icons only: `tv`, `clipboard-outline` and
    # `flame-outline` wait in UI-REQUESTS.md. Each entry is also a tab of the app's pages and opens
    # with its permission: Stations and Settings, to whoever may change them.
    navigation = [
        Nav("display", _("Display"), "ion:desktop-outline", "/kitchen/display", permission="kitchen.view_ticket"),
        Nav("tickets", _("Tickets"), "ion:list-outline", "/kitchen/tickets", permission="kitchen.view_ticket"),
        Nav("stations", _("Stations"), "ion:layers-outline", "/kitchen/stations", permission="kitchen.manage_station"),
        Nav(
            "history", pgettext_lazy("kitchen menu", "History"), "ion:time-outline", "/kitchen/history",
            permission="kitchen.view_log",
        ),
        Nav(
            "settings", _("Settings"), "ion:settings-outline", "/kitchen/settings",
            permission="kitchen.change_settings",
        ),
    ]
    # KITCHEN-F05/F16: every new ticket tells the installed device; a tap opens the kitchen display.
    notices = [
        DeviceNotice(
            key="received",
            operation="kitchen.ticket.notices",
            title=[_("New kitchen ticket · {label}"), _("New kitchen ticket · {number}")],
            body=NOTICE_BODY,
            route="/kitchen/display",
            permission="kitchen.view_ticket",
            refresh_on=NOTICE_EVENTS,
        )
    ]
    help = Help()
