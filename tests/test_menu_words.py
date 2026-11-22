"""The words of the menu entries that are also the tabs of their app's pages.

An app's tab bar is the part of its menu the person may open (``useAppTabs`` reads it from ``base.session.me``), so a
tab says what its menu entry says, in the reader's language. These are the words each tab said when the app still
wrote its own list: people learnt them on the till and in the kitchen, and they stay the same in English and in
Spanish.
"""

import pytest
from django.utils import translation
from live.meta import module_configs

WORDS = [
    ("/attendance/clock", "Clock in", "Fichar"),
    ("/attendance/records", "Records", "Registros"),
    ("/cart_checkout/carts", "Carts", "Carritos"),
    ("/cart_checkout/orders", "Orders", "Pedidos"),
    ("/invoice/invoices", "Invoices", "Facturas"),
    ("/invoice/series", "Series", "Series"),
    ("/kitchen/display", "Display", "Pantalla"),
    ("/kitchen/tickets", "Tickets", "Comandas"),
    ("/kitchen/stations", "Stations", "Estaciones"),
    ("/kitchen/history", "History", "Historial"),
    ("/online_booking/bookings", "Bookings", "Reservas"),
    ("/payment/payments", "Payments", "Pagos"),
    ("/reservation/reservations", "Reservations", "Reservas"),
    ("/reservation/waitlist", "Waitlist", "Lista de espera"),
    ("/reservation/availability", "Availability", "Disponibilidad"),
    ("/sale/pos", "Sell", "Vender"),
    ("/sale/sales", "Sales", "Ventas"),
    ("/sale/quick-notes", "Quick notes", "Notas rápidas"),
    # «Departamentos» does not fit a fifth of a phone's tab bar.
    ("/sale/departments", "Sections", "Secciones"),
    ("/sale/settings", "Settings", "Ajustes"),
    ("/schedule/hours", "Hours", "Horario"),
    ("/schedule/special-days", "Special days", "Días especiales"),
    ("/schedule/settings", "Settings", "Ajustes"),
    ("/service/services", "Services", "Servicios"),
    ("/service/categories", "Categories", "Categorías"),
    ("/service/packages", "Packages", "Bonos y paquetes"),
    ("/staff/members", "Staff", "Personal"),
    ("/staff/roles", "Roles", "Roles"),
    ("/staff/time-off", "Time Off", "Ausencias"),
    ("/staff/schedules", "Schedules", "Horarios"),
    ("/table/floor-plan", "Floor plan", "Plano de sala"),
    ("/table/zones", "Zones", "Zonas"),
    ("/table/tables", "Tables", "Mesas"),
    ("/table/sessions", "Sessions", "Sesiones"),
    ("/task/tasks", "Tasks", "Tareas"),
    ("/task/projects", "Projects", "Proyectos"),
]


def entry(path: str):
    return next(nav for config in module_configs() for nav in config.navigation if nav.path == path)


@pytest.mark.parametrize(("path", "english", "spanish"), WORDS)
def test_a_tab_says_in_both_languages_what_it_always_said(path, english, spanish):
    label = entry(path).label
    with translation.override("en"):
        assert str(label) == english
    with translation.override("es"):
        assert str(label) == spanish
