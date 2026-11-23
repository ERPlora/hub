"""What the assistant is asked about apps, settings, the theme, names and payments, in phrases that once reached no tool.

A turn offers the twenty tools the person's words name best. Some phrases bring theirs in, though not always first; for
the rest the model searches the whole catalogue for the task (``base.assistant.find_tools``) and the next step of the
same request offers what the search found.
"""

import pytest
from live import assistant as shared

from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import offered, owner_of_a
from base.tests.test_assistant_tool_search import (
    test_the_tool_a_phrase_left_out_is_offered_once_the_model_searches_for_it as offered_once_searched,
)
from base.tests.test_assistant_tool_search import user

__all__ = ["in_business_a"]

pytestmark = HUB_DB  # the catalogue is of the apps on in the business (base.activation)

RECIPE_OFF = "flow.recipe.disable"
RECIPE_ON = "flow.recipe.enable"
THEME = "base.profile.preferences_set"
APP_ON = "base.app.enable"
RENAME_FLOW = "flow.flow.update"

#: Phrases whose own words bring the tool they ask for into the twenty a turn offers.
OFFERED = [
    pytest.param(
        "es",
        ("apaga el sonido de la cocina", "desactiva el temporizador de la cocina"),
        "kitchen.settings.update",
        id="live-98-kitchen",
    ),
    pytest.param("es", ("desactiva la zona Terraza",), "table.zone.update", id="live-98-zone"),
    pytest.param("es", ("desactiva el campo Talla",), "customer.field.update", id="live-98-field"),
    pytest.param(
        "es",
        (
            "desactiva hoy los recordatorios de las citas",
            "por favor desactiva los recordatorios automáticos de citas",
            "no quiero que se manden recordatorios de citas, desactívalos",
            "desactiva los recordatorios por WhatsApp",
            "apaga los recordatorios por correo de las reservas",
            "apaga temporalmente los recordatorios de citas",
        ),
        RECIPE_OFF,
        id="live-100",
    ),
    pytest.param(
        "en", ("turn off the dark mode", "turn on the dark mode", "switch on the light mode"), THEME, id="live-102"
    ),
    pytest.param(
        "es",
        ("quita el modo oscuro", "activa el modo noche", "desactiva el modo nocturno", "pon la app en oscuro"),
        THEME,
        id="live-107",
    ),
    pytest.param(
        "es",
        (
            "pon Clientes en el menú",
            "pon Mesas en el menú",
            "pon Reservas en el menú",
            "pon Caja en el menú",
            "añade Mesas al menú",
        ),
        APP_ON,
        id="live-165-es",
    ),
    pytest.param("en", ("add Tables to the menu",), APP_ON, id="live-165-en"),
    pytest.param("es", ("quita del menú Clientes",), "base.app.disable", id="live-165-off"),
    pytest.param("es", ("renombra Bienvenida como «Clientes nuevos»",), RENAME_FLOW, id="live-157-es"),
    pytest.param(
        "es", ("renombra la lista Verano como «Nueva temporada»",), "pricing.price_list.update", id="live-157-list"
    ),
    pytest.param("en", ("rename the old iPad to Kitchen",), "base.device.rename", id="live-157-device"),
]

#: What a phrase's own words leave out, and the task the model searches for then, in English and in Spanish. The search
#: reads the words as a turn does: a switch is found by turning it off or on, not by pausing or resuming it.
REMINDERS_OFF = ("turn off the appointment reminders", "desactivar los recordatorios de citas")
REMINDERS_ON = ("turn on the appointment reminders", "activar los recordatorios de citas")
QUICK_NOTE = ("create a quick note", "crear una nota rápida")
SEARCHED = [
    pytest.param("es", "pausa los recordatorios de citas", REMINDERS_OFF, RECIPE_OFF, id="live-97-es"),
    pytest.param("es", "suspende los recordatorios de citas", REMINDERS_OFF, RECIPE_OFF, id="live-97-es-suspende"),
    pytest.param("en", "pause the appointment reminders", REMINDERS_OFF, RECIPE_OFF, id="live-97-en"),
    pytest.param(
        "es", "quiero que desactives los recordatorios de las citas", REMINDERS_OFF, RECIPE_OFF, id="live-100-quiero"
    ),
    pytest.param("en", "set up a 'no onion' quick note", QUICK_NOTE, "sale.quick_note.create", id="live-166-quick-note"),
    pytest.param(
        "en", "set up a quick note that says 'no onion'", QUICK_NOTE, "sale.quick_note.create", id="live-166-says"
    ),
    pytest.param(
        "en",
        "set up the 'No cilantro' warning so I can tap it quickly when keying in dishes",
        QUICK_NOTE,
        "sale.quick_note.create",
        id="live-166-cilantro",
    ),
    pytest.param(
        "en",
        "set up Bizum as a payment method",
        ("create a payment method", "crear un método de pago"),
        "sale.payment_method.create",
        id="live-166-payment",
    ),
    pytest.param("en", "stop the appointment reminders", REMINDERS_OFF, RECIPE_OFF, id="live-97-stop"),
    pytest.param(
        "es",
        "quita los recordatorios de las citas, que molestan a los clientes",
        REMINDERS_OFF,
        RECIPE_OFF,
        id="live-97-remove",
    ),
    pytest.param("es", "reanuda los recordatorios de citas", REMINDERS_ON, RECIPE_ON, id="live-97-reanuda"),
    pytest.param("en", "resume the appointment reminders", REMINDERS_ON, RECIPE_ON, id="live-97-resume"),
    pytest.param(
        "en",
        "set up a Drinks section",
        ("create a section", "crear una sección"),
        "sale.department.create",
        id="live-166-section",
    ),
    pytest.param(
        "en",
        "rename Welcome to «New customers»",
        ("rename an automation", "renombrar una automatización"),
        RENAME_FLOW,
        id="live-157-en",
    ),
    pytest.param(
        "es",
        "¿con qué pagan los clientes?",
        ("list the payment methods", "ver los medios de pago"),
        "sale.payment_method.list",
        id="live-171",
    ),
    pytest.param(
        "es",
        "activa el envío real a la AEAT comprobando antes que la cuenta y la autorización estén listas",
        ("turn on real sending to the AEAT", "activar el envío real a la AEAT"),
        "verifactu.config.go_live",
        id="live-173",
    ),
]


@pytest.mark.parametrize(("language", "phrases", "expected"), OFFERED)
def test_the_phrase_alone_brings_its_tool_into_the_turn(make_user, language, phrases, expected):
    context = owner_of_a(make_user, language)
    for said in phrases:
        assert shared.tool_name(expected) in offered(context, user(said)), said


@pytest.mark.parametrize(("language", "said", "tasks", "expected"), SEARCHED)
def test_the_tool_the_phrase_leaves_out_arrives_once_the_model_searches_for_the_task(
    make_user, language, said, tasks, expected
):
    offered_once_searched(make_user, language, said, tasks, expected)
