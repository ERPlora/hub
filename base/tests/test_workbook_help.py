"""base/workbook_help.py: a module's help window read from the customer's part of its WORKBOOK.

The reading is the same in every language: the words come from ``Words`` (base's ``workbook`` vocabulary in the file's
language) and the tab labels from the module's menu, so a third language that no catalogue knows reads like the two
the Hub speaks today.
"""

import pytest
from django.utils import translation

from base.catalog import user_part
from base.tests.help_workbooks import (
    EN,
    EN_TABS,
    EN_WORDS,
    EO,
    EO_TABS,
    EO_WORDS,
    ES,
    ES_TABS,
    ES_WORDS,
    header_of,
    write_workbooks,
)
from base.workbook_help import SOURCE_LANGUAGE, Draft, Flow, Screen, parse, workbook, words


def spanish():
    return parse(user_part(ES), ES_TABS, ES_WORDS)


class TestWhatItIsFor:
    def test_it_is_the_first_section_with_the_lines_of_each_list_item_joined(self):
        assert spanish().purpose == (
            "Mesas es el **plano de la sala**: sus zonas y sus mesas.\n"
            "\n"
            "Quién la usa:\n"
            "\n"
            "- El **responsable** dibuja el plano y cambia el aforo de cada mesa.\n"
            "- El **empleado** sienta a la gente.\n"
            "\n"
            "```\n"
            "## Esto no es un encabezado\n"
            "```"
        )


FENCE = "`" * 3


@pytest.mark.parametrize(
    ("written", "painted"),
    [
        ("Una frase que sigue\nen la línea de abajo\ny en otra.", "Una frase que sigue en la línea de abajo y en otra."),
        ("Un párrafo.\n\nOtro párrafo.", "Un párrafo.\n\nOtro párrafo."),
        ("Acaba en dos espacios  \nsigue aparte.", "Acaba en dos espacios\nsigue aparte."),
        ("Acaba en una barra\\\nsigue aparte.", "Acaba en una barra\nsigue aparte."),
        ("- Un elemento\n- Otro elemento", "- Un elemento\n- Otro elemento"),
        ("- Un elemento que sigue\nsin sangría.", "- Un elemento que sigue sin sangría."),
        ("Antes de la tabla:\n| a | b |\n|---|---|\n| 1 | 2 |", "Antes de la tabla:\n| a | b |\n|---|---|\n| 1 | 2 |"),
        ("Antes de la cita:\n> una cita\n> que sigue", "Antes de la cita:\n> una cita\n> que sigue"),
        ("Antes de la ventana\n#### Ventana\nSu texto\nsigue.", "Antes de la ventana\n#### Ventana\nSu texto sigue."),
        (f"Antes del código:\n{FENCE}\nuna línea\notra\n{FENCE}", f"Antes del código:\n{FENCE}\nuna línea\notra\n{FENCE}"),
        ("Antes de la raya\n---\ndespués.", "Antes de la raya\n---\ndespués."),
    ],
    ids=["wrapped", "paragraphs", "two-spaces", "backslash", "items", "lazy-item", "table", "quote", "heading", "code", "rule"],
)
def test_a_paragraph_is_one_line_however_the_file_wraps_it(written, painted):
    # The window paints a paragraph keeping its line breaks, so a break the file makes to fit its width is a space.
    assert parse(f"## Para qué sirve\n\n{written}\n", ES_TABS, ES_WORDS).purpose == painted


@pytest.mark.parametrize(
    ("written", "published"),
    [
        ("sin nombre, no se activa.", "Sin nombre, no se activa."),
        ("él no puede.", "Él no puede."),
        ("1. pulsa «+».", "1. pulsa «+»."),
        ("`zona` vacía.", "`zona` vacía."),
        ("«Ya hay una zona».", "«Ya hay una zona»."),
    ],
    ids=["lowercase", "accented", "list", "code", "quote"],
)
def test_the_steps_and_what_happens_if_it_fails_start_with_a_capital(written, published):
    flow = f"## Flujos\n\n### TABLE-F01 Crear\nEstado: hecho\nPantalla: Zonas\nPasos: {written}\nSi falla: {written}\n"
    [read] = parse(flow, ES_TABS, ES_WORDS).flows
    assert (read.steps, read.failure) == (published, published)


class TestScreens:
    def test_each_tab_publishes_its_summary_in_the_order_of_the_menu_without_its_windows(self):
        assert spanish().screens == (
            Screen(
                "floor_plan",
                "Plano de sala",
                "/table/floor-plan",
                "Tocar una mesa abre su ventana:\n"
                "\n"
                "- libre: pregunta los comensales y la sienta.\n"
                "  - con reserva: dice a nombre de quién.",
            ),
            Screen("zones", "Zonas", "/table/zones", "Una tabla con el nombre y el color de cada zona."),
            Screen("settings", "Ajustes", "/table/settings", "Los avisos de tiempo."),
        )

    def test_the_summary_ends_at_the_first_window_not_at_a_heading_inside_code(self):
        section = f"## Pantallas\n\n### Zonas\nUna tabla:\n{FENCE}\n#### no es una ventana\n{FENCE}\n\n#### Nueva\nPide.\n"
        [screen] = parse(section, ES_TABS, ES_WORDS).screens
        assert screen.text == f"Una tabla:\n{FENCE}\n#### no es una ventana\n{FENCE}"

    def test_they_follow_the_menu_whatever_order_the_workbook_writes_them_in(self):
        read = parse(user_part(ES), tuple(reversed(ES_TABS)), ES_WORDS)
        assert [screen.id for screen in read.screens] == ["settings", "zones", "floor_plan"]

    def test_a_section_that_names_no_tab_is_set_aside_and_a_tab_without_one_is_left_out(self):
        read = spanish()
        assert read.unknown_screens == ("Pantalla retirada",)
        assert "tables" not in [screen.id for screen in read.screens]

    def test_a_tab_written_twice_keeps_its_first_section_and_says_so(self):
        twice = user_part(ES).replace("### Ajustes\n", "### Zonas\nOtra tabla.\n\n### Ajustes\n", 1)
        read = parse(twice, ES_TABS, ES_WORDS)
        assert read.repeated_screens == ("Zonas",)
        assert read.screens[1].text == "Una tabla con el nombre y el color de cada zona."
        assert spanish().repeated_screens == ()

    def test_without_the_screens_heading_there_are_no_screens(self):
        read = parse(user_part(ES.replace("## Pantallas", "## Otra cosa")), ES_TABS, ES_WORDS)
        assert (read.screens, read.unknown_screens) == ((), ())


class TestFlows:
    def test_a_flow_publishes_its_title_without_its_id_its_steps_and_what_happens_if_it_fails(self):
        assert spanish().flows[0] == Flow(
            "TABLE-F01",
            "Crear una zona",
            ("zones",),
            "1. En **Mesas → Zonas** pulsa «+» y escribe el nombre, que después sale como pestaña del plano.\n"
            "2. Pulsa «Añadir zona».",
            "Sin nombre, el botón no se activa. Un nombre repetido dice «Ya hay una zona con ese nombre.».",
        )

    def test_its_screen_names_tabs_without_what_goes_in_parentheses_commas_included(self):
        by_id = {flow.id: flow for flow in spanish().flows}
        assert by_id["TABLE-F02"].screens == ("floor_plan",)

    def test_a_window_of_a_tab_names_that_tab_in_the_order_the_screen_names_them(self):
        by_id = {flow.id: flow for flow in spanish().flows}
        assert by_id["TABLE-F03"].screens == ("floor_plan", "zones")

    def test_a_flow_without_what_happens_if_it_fails_has_it_empty(self):
        by_id = {flow.id: flow for flow in spanish().flows}
        assert (by_id["TABLE-F02"].steps, by_id["TABLE-F02"].failure) == ("1. Toca la mesa ocupada.\n2. Pulsa «Cobrar».", "")

    def test_only_the_flows_that_are_done_on_a_tab_of_the_customer_s_part_are_published(self):
        # F04 is not done, F05 is done on no screen, F06 is below the customer's part.
        assert [flow.id for flow in spanish().flows] == ["TABLE-F01", "TABLE-F02", "TABLE-F03"]

    def test_what_is_not_published_is_kept_aside_with_its_status_and_the_tabs_it_names(self):
        assert spanish().unpublished == (
            Draft("TABLE-F04", "no hecho — falta la pantalla", ("zones",)),
            Draft("TABLE-F05", "hecho", ()),
        )

    @pytest.mark.parametrize(
        ("status", "done"),
        [
            ("hecho", True),
            ("hecho — sin preguntar los comensales en el TPV", True),
            ("hecho: también por la API", True),
            ("hecho (servidor y pantalla)", True),
            ("hecho - en la tableta", True),
            ("no hecho", False),
            ("no hecho — falta la pantalla", False),
            ("parcial — sin la ventana", False),
            ("hecho en Mesas (TABLE-F15): la cuenta no cambia", False),
        ],
    )
    def test_a_flow_is_done_when_its_status_before_any_note_is_the_done_word(self, status, done):
        flow = f"## Flujos\n\n### TABLE-F01 Crear una zona\nEstado: {status}\nPantalla: Zonas\nPasos:\n1. Pulsa «+».\n"
        assert bool(parse(flow, ES_TABS, ES_WORDS).flows) is done

    def test_nothing_but_its_title_steps_and_failure_leaves_a_flow(self):
        published = repr(spanish().flows)
        for internal in ("table.zone.created", "el nombre y el color", "responsable", "restaurante", "cobra la mesa 4"):
            assert internal not in published


@pytest.mark.parametrize(
    ("markdown", "tabs", "vocabulary", "screens", "flows"),
    [
        (user_part(ES), ES_TABS, ES_WORDS, ["floor_plan", "zones", "settings"], ["TABLE-F01", "TABLE-F02", "TABLE-F03"]),
        (EN, EN_TABS, EN_WORDS, ["floor_plan", "zones", "settings"], ["TABLE-F01", "TABLE-F02", "TABLE-F03"]),
        (EO, EO_TABS, EO_WORDS, ["floor_plan", "zones"], ["TABLE-F01", "TABLE-F02"]),
    ],
    ids=["es", "en", "eo"],
)
def test_every_language_reads_alike_with_its_own_words_and_labels(markdown, tabs, vocabulary, screens, flows):
    read = parse(markdown, tabs, vocabulary)
    assert [screen.id for screen in read.screens] == screens
    assert [flow.id for flow in read.flows] == flows
    assert read.flows[0].screens == ("zones",)
    assert read.flows[1].screens == ("floor_plan",)


def test_the_third_language_joins_its_list_lines_and_maps_a_window_to_its_tab():
    read = parse(EO, EO_TABS, EO_WORDS)
    assert read.flows[0].steps == "1. Tuŝu «+» kaj skribu la nomon, kiu poste aperas en la plano."
    assert read.flows[0].failure == "Sen nomo, la butono restas malŝaltita."
    assert read.screens[0].title == "Salonplano"


class TestWords:
    @pytest.mark.parametrize(("language", "expected"), [("es", ES_WORDS), ("en", EN_WORDS)])
    def test_they_are_base_s_vocabulary_in_the_active_language(self, language, expected):
        with translation.override(language):
            assert words() == expected

    def test_a_language_no_catalogue_knows_gets_the_source_words_of_the_code(self):
        with translation.override("eo"):
            assert words() == EN_WORDS


class TestWhichFile:
    def test_the_source_language_reads_the_customer_s_part_of_workbook_md(self, tmp_path):
        write_workbooks(tmp_path, {"en": EN})
        assert workbook(tmp_path, SOURCE_LANGUAGE) == (SOURCE_LANGUAGE, user_part(ES))

    @pytest.mark.parametrize(("language", "body"), [("en", EN), ("eo", EO)])
    def test_another_language_reads_its_own_file_while_it_is_current(self, tmp_path, language, body):
        write_workbooks(tmp_path, {"en": EN, "eo": EO})
        assert workbook(tmp_path, language) == (language, body)

    def test_a_regional_language_reads_its_own_file_else_its_base_language_s(self, tmp_path):
        write_workbooks(tmp_path, {"en": EN})
        assert workbook(tmp_path, "en-gb") == ("en", EN)
        write_workbooks(tmp_path, {"en": EN, "en-gb": EN.replace("colour", "color")})
        assert workbook(tmp_path, "en-gb") == ("en-gb", EN.replace("colour", "color"))

    def test_a_regional_variant_of_the_source_language_reads_the_source(self, tmp_path):
        write_workbooks(tmp_path, {"en": EN})
        assert workbook(tmp_path, "es-mx") == (SOURCE_LANGUAGE, user_part(ES))

    def test_a_language_without_its_file_reads_the_source(self, tmp_path):
        write_workbooks(tmp_path, {"en": EN})
        assert workbook(tmp_path, "eo") == (SOURCE_LANGUAGE, user_part(ES))

    @pytest.mark.parametrize(
        "first_line",
        [header_of(ES.replace("sus zonas", "sus salas")), "## What it is for and who it is for", ""],
        ids=["another-hash", "no-header", "empty"],
    )
    def test_a_file_that_is_not_current_with_the_source_reads_the_source(self, tmp_path, first_line):
        write_workbooks(tmp_path, {})
        (tmp_path / "WORKBOOK.en.md").write_text(f"{first_line}\n\n{EN}", encoding="utf-8")
        assert workbook(tmp_path, "en") == (SOURCE_LANGUAGE, user_part(ES))
