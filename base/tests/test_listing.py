"""Names said together as the screens say them: ordered as the browser orders them (``localeCompare``) and joined as
its ``Intl.ListFormat`` joins them in the person's language. Each expected text is what the browser writes."""

import pytest

from base import listing


@pytest.mark.parametrize(
    ("language", "names", "said"),
    [
        ("es", ["Mesas"], "Mesas"),
        ("es", ["Clientes", "Impuestos"], "Clientes e Impuestos"),
        ("es", ["Clientes", "Horarios", "Impuestos"], "Clientes, Horarios e Impuestos"),
        ("es", ["Horarios", "Mesas"], "Horarios y Mesas"),
        ("es", ["Ventas", "Hilo"], "Ventas e Hilo"),
        ("es", ["Ventas", "hilo"], "Ventas e hilo"),
        ("es", ["Ventas", "Hi"], "Ventas e Hi"),
        ("es", ["Mesas", "Hielo"], "Mesas y Hielo"),
        ("es", ["Ventas", "Hia"], "Ventas y Hia"),
        ("es", ["Ventas", "Íñigo"], "Ventas y Íñigo"),
        ("en", ["Customers", "Taxes"], "Customers and Taxes"),
        ("en", ["Customers", "Sales & POS", "Taxes"], "Customers, Sales & POS, and Taxes"),
        ("es-es", ["Clientes", "Impuestos"], "Clientes e Impuestos"),
    ],
)
def test_names_are_joined_as_the_browser_joins_a_list_in_that_language(language, names, said):
    assert listing.joined(names, language) == said


def test_no_names_say_nothing():
    assert listing.joined([], "es") == ""


@pytest.mark.parametrize(
    ("names", "ordered"),
    [
        (["Catering", "Catálogo"], ["Catálogo", "Catering"]),
        (["Zona", "clientes", "Catering"], ["Catering", "clientes", "Zona"]),
        (["Ventas / TPV", "Impuestos", "Clientes"], ["Clientes", "Impuestos", "Ventas / TPV"]),
    ],
)
def test_names_are_ordered_as_the_browser_orders_them(names, ordered):
    assert listing.ordered(names) == ordered
