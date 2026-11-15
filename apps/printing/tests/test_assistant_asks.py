"""What layer 1 of the assistant's QA says of Printing: how many tools it offers, the writes the real-model QA found
unreachable, and a person's own words for each ask of its tools.

Every ask of every tool of printing bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(printing is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""


import pytest
from live.operations import AI, registry

from base.models import Membership
from base.tests.test_assistant_asks import assert_its_asks_bring, english_coverage_test, place_of_no_ask
from base.tests.test_assistant_asks import english_words_test, own_words_test, said_in_spanish_too_test
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

#: What only who runs the business does: an employee's assistant is never offered the printers' settings.
NOT_THE_EMPLOYEES = {
    "printing.printer.create",
    "printing.printer.update",
    "printing.settings.update",
    "printing.device.register",
    "printing.device.retire",
}
def test_printing_offers_at_least_20_tools():
    """Printing's tools are at least 20 (``AI``, never ``INTERNAL``): a silent drop of tools fails."""
    tools = {
        name
        for name, op in registry.items()
        if op.app_label == "printing" and isinstance(op.ai_spec(), AI)
    }
    assert len(tools) >= 20


@pytest.mark.django_db
def test_an_employee_is_never_offered_the_printers_settings(catalog_of):
    owner = catalog_of(Membership.Role.OWNER, "es")
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert NOT_THE_EMPLOYEES <= set(owner)
    assert NOT_THE_EMPLOYEES.isdisjoint(employee)
    assert (
        "printing.printer.test" in employee
    )  # positive control: printing is the employee's own door


#: The requests of hub#1086's QA as the person said them (``tests/e2e/qa/probes/*-es-printing-2026-11-08.json``), with
#: the role that said each, and nothing of the tools' ``asks``: before Printing said its asks, none of these tools was
#: among the ones a turn offers (``MAX_TOOLS``), so the model answered it had no tool. Now a turn offers all of them
#: (measured on this branch: the test page 16th, the printer change 25th, the employee's devices 9th): the model can
#: choose them, and their words stay the person's, never the asks'
#: (``test_no_ask_copies_a_qa_probe_or_names_a_qa_record``).
REPORTED = [
    (
        Membership.Role.OWNER,
        "printing.printer.test",
        "saca una página de prueba en Caja QA para comprobar la conexión y el papel",
    ),  # qa20261108.owner.es.printing.printer.test
    (
        Membership.Role.OWNER,
        "printing.printer.update",
        "cambia Caja QA a la IP 192.168.1.241, papel de 58 mm y renómbrala «Caja barra QA»",
    ),  # qa20261108.owner.es.printing.printer.update
    (
        Membership.Role.EMPLOYEE,
        "printing.device.list",
        "¿qué equipos hay registrados para imprimir los tickets del negocio?",
    ),  # qa20261108.employee.es.printing.device.list
]


@pytest.mark.django_db
@pytest.mark.parametrize(("role", "name", "phrase"), REPORTED)
def test_the_reported_printing_requests_are_offered_their_tool_without_being_its_asks(catalog_of, role, name, phrase):
    assert place_of_no_ask(catalog_of(role, "es"), name, phrase) is not None


#: A device that prints, retired in words that are no ask nor probe and that only its tool's asks bring among the first
#: ten: «dispositivo» is the Hub's own word for it (Printing → Devices, «Dispositivo 1»). In live, «retira» asks to
#: retire, delete, remove and withdraw, and «el equipo» reads as the staff (``live.assistant.SYNONYMS``), so an ask that
#: said «retira el equipo Barra 2» fell to the edge of the ten (10th) and this phrase with it (13th). With «el
#: dispositivo» in the ask it is 8th for the owner, the admin and the manager, and 13th without its asks; it shares one
#: stem with an ask («dispositivo») and says no «retira», which brings the tool by its own name.
OWN_WORDS = [
    ("es", "printing.device.retire", "ese dispositivo de la entrada desapareció; que no imprima nunca más"),
]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN, Membership.Role.MANAGER])
@pytest.mark.parametrize(("language", "name", "phrase"), OWN_WORDS)
def test_a_retired_device_in_the_persons_own_words_reaches_its_tool_by_its_asks(
    catalog_of, role, language, name, phrase
):
    assert_its_asks_bring(catalog_of(role, language), name, phrase, language)


#: What the owner says in words of their own for each Spanish ask of Printing that says a word no other ask of its tool
#: says, synonyms included: only that ask brings the phrase among the first ten, so emptying or overwriting any one of
#: them fails here. None says «equipo» or «trabajo» (the Hub reads both as the staff), and the asks that share every
#: word with another of their tool have no phrase: nothing a person says depends on them alone.
OWN_WORDS_ES = [
    ("printing.device.coverage", "¿hay alguna función que no tenga a nadie?"),
    ("printing.device.coverage", "¿alguien está cubriendo la barra esta noche?"),
    ("printing.device.detail", "¿a dónde llega Terraza 1?"),
    ("printing.device.detail", "¿quién configuró el portátil para imprimir?"),
    ("printing.device.list", "¿desde dónde imprimimos?"),
    ("printing.device.list", "¿cuáles se vieron hace poco?"),
    ("printing.device.register", "deja esta tablet para los tickets"),
    ("printing.device.retire", "hemos perdido la tableta de la terraza, que no vuelva a imprimir"),
    ("printing.device.update", "la tablet de la barra ahora se llamará Barra Norte"),
    ("printing.device.update", "haz que la tablet de la terraza también sirva para bebidas"),
    ("printing.job.cancel", "lo que se ha atascado, que no salga"),
    ("printing.job.claim", "la tablet de la terraza recoge el siguiente"),
    ("printing.job.claim", "que la terraza coja el más antiguo"),
    ("printing.job.complete", "ya salió bien por la tablet de la terraza"),
    ("printing.job.complete", "ya está hecho en la tablet de la terraza"),
    ("printing.job.create", "imprímeme la etiqueta del vino en formato A4"),
    ("printing.job.create", "manda esto en formato A4"),
    ("printing.job.fail", "la tablet de la terraza avisa: no salió"),
    ("printing.job.fail", "se quedó sin papel a mitad"),
    ("printing.job.get", "¿qué pasó con la impresión de la terraza?"),
    ("printing.job.get", "¿en qué estado está la F-000045?"),
    ("printing.job.list", "repasemos la cola"),
    ("printing.job.list", "¿cuáles fallaron hoy?"),
    ("printing.job.list", "lista los documentos pendientes"),
    ("printing.job.retry", "reintenta el documento que tiene la referencia F-000210"),
    ("printing.job.retry", "vuelve a mandar lo de la terraza"),
    ("printing.job.retry", "reenvía lo atascado"),
    ("printing.job.summary", "¿qué tal va la cola?"),
    ("printing.job.summary", "¿se ha atascado alguna?"),
    ("printing.job.summary", "¿se están imprimiendo bien las comandas?"),
    ("printing.printer.create", "tenemos otra llamada Barra 3 en el puerto 9100"),
    ("printing.printer.create", "quiero dar de alta otra para la caja"),
    ("printing.printer.create", "conecta una de etiquetas con la IP 192.168.1.60"),
    ("printing.printer.get", "háblame de Barra 3, ¿cómo está?"),
    ("printing.printer.get", "¿qué papel usa Barra 3?"),
    ("printing.printer.list", "¿con qué impresoras cuenta la cocina?"),
    ("printing.printer.status", "¿está funcionando la de cocina hoy?"),
    ("printing.printer.status", "¿cuándo fue la última vez que sacó algo la de la barra?"),
    ("printing.printer.test", "saca una página A4 en la impresora de la terraza"),
    ("printing.printer.test", "manda algo a la impresora de la terraza, a ver si sale"),
    ("printing.printer.update", "que Barra 3 pase a llamarse Recepción"),
    ("printing.settings.get", "¿qué opciones están activadas en los ajustes?"),
    ("printing.settings.get", "¿cuál dejamos elegida para el mostrador?"),
    ("printing.settings.get", "¿cómo está configurado todo?"),
    ("printing.settings.update", "que se imprima solo"),
    ("printing.settings.update", "las etiquetas, que las mande a Cocina 2"),
    ("printing.settings.update", "dos de cada, por favor"),
    ("printing.settings.update", "el cajón tiene que abrirse al cobrar"),
]
test_a_request_in_the_persons_own_words_reaches_its_tool_by_its_asks = own_words_test(OWN_WORDS_ES, "es")


#: The same in English, for each English ask with a word of its own: the tool's English asks lift it among the first
#: ten, and only that ask does. None names the thing by a word another English ask of its tool says («printer»,
#: «station», «job»), or that ask would keep the lift when this one is overwritten.
OWN_WORDS_EN = [
    ("printing.device.coverage", "is some function still with nobody behind it?"),
    ("printing.device.coverage", "is anybody covering the labels today?"),
    ("printing.device.detail", "what can the Terrace 1 tablet reach?"),
    ("printing.device.detail", "did the terrace tablet report in?"),
    ("printing.device.list", "which tablets are registered here?"),
    ("printing.device.list", "each tablet we print from, please"),
    ("printing.device.register", "enroll this laptop under its name"),
    ("printing.device.register", "the counter tablet takes care of printing"),
    ("printing.device.retire", "the bar tablet is gone for good"),
    ("printing.device.retire", "we lost the patio tablet; it's out of service now"),
    ("printing.device.update", "rename the bar tablet"),
    ("printing.device.update", "the terrace tablet should reach the kitchen as well"),
    ("printing.job.cancel", "forget that job, it shouldn't come out"),
    ("printing.job.cancel", "drop that stuck one"),
    ("printing.job.claim", "give me the next one for the terrace tablet"),
    ("printing.job.claim", "ready for the oldest one"),
    ("printing.job.complete", "that one came out fine"),
    ("printing.job.complete", "the terrace tablet is done with it"),
    ("printing.job.create", "I need a label for this bottle"),
    ("printing.job.create", "send this to the kitchen, two copies"),
    ("printing.job.fail", "the terrace device says it didn't come out"),
    ("printing.job.fail", "it ran dry of paper midway"),
    ("printing.job.get", "what happened to that job?"),
    ("printing.job.retry", "retry table 4's one"),
    ("printing.job.retry", "put table 4's one back in the queue again"),
    ("printing.job.retry", "reprint that stuck one"),
    ("printing.job.summary", "how's it all going today?"),
    ("printing.job.summary", "is something stuck?"),
    ("printing.job.summary", "is the queue ok?"),
    ("printing.printer.create", "we've got one on the network called Bar 3"),
    ("printing.printer.create", "connect one for labels"),
    ("printing.printer.get", "what did the technician tell you about the state of Bar 3?"),
    ("printing.printer.status", "is Kitchen 2 working?"),
    ("printing.printer.status", "why won't the till one print?"),
    ("printing.printer.status", "the bar one: last print when?"),
    ("printing.printer.test", "run a page through Kitchen 2"),
    ("printing.printer.test", "send a sheet to Bar 3 with its address"),
    ("printing.printer.update", "Terrace 3 now sits at the front desk, same address"),
    ("printing.printer.update", "switch Terrace 3's connection to bluetooth"),
    ("printing.printer.update", "deactivate the old bar one's connection, it takes no new jobs"),
    ("printing.settings.update", "let the receipt come out by itself"),
    ("printing.settings.update", "send what goes to the kitchen to Kitchen 3"),
    ("printing.settings.update", "two of every receipt, please"),
]
test_a_request_in_english_is_lifted_by_its_english_asks = english_words_test(OWN_WORDS_EN)

#: The tools whose English asks say nothing their Spanish asks, description or name do not: no English phrase depends
#: on them, so what sees them change is the words they say only in English.
SAID_IN_SPANISH_TOO = ["printing.job.list", "printing.printer.list", "printing.settings.get"]
test_the_english_asks_that_say_nothing_new_keep_saying_nothing_new = said_in_spanish_too_test(SAID_IN_SPANISH_TOO)
test_each_tool_has_its_own_english_words = english_coverage_test(
    "printing", list(dict(OWN_WORDS_EN).items()), also=SAID_IN_SPANISH_TOO
)
