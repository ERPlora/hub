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
from base.workbook_help import SOURCE_LANGUAGE, Flow, Screen, parse, workbook, words


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


class TestScreens:
    def test_each_tab_with_its_section_in_the_order_of_the_menu_its_windows_inside(self):
        assert spanish().screens == (
            Screen(
                "floor_plan",
                "Plano de sala",
                "/table/floor-plan",
                "Tocar una mesa abre su ventana:\n"
                "\n"
                "- libre: pregunta los comensales y la sienta.\n"
                "  - con reserva: dice a nombre de quién.\n"
                "\n"
                "#### Cobrar mesa\n"
                "Pide el importe y cobra.",
            ),
            Screen("zones", "Zonas", "/table/zones", "Una tabla con el nombre y el color de cada zona."),
            Screen("settings", "Ajustes", "/table/settings", "Los avisos de tiempo."),
        )

    def test_they_follow_the_menu_whatever_order_the_workbook_writes_them_in(self):
        read = parse(user_part(ES), tuple(reversed(ES_TABS)), ES_WORDS)
        assert [screen.id for screen in read.screens] == ["settings", "zones", "floor_plan"]

    def test_a_section_that_names_no_tab_is_set_aside_and_a_tab_without_one_is_left_out(self):
        read = spanish()
        assert read.unknown_screens == ("Pantalla retirada",)
        assert "tables" not in [screen.id for screen in read.screens]

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
            "sin nombre, el botón no se activa.",
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
    assert read.flows[0].failure == "sen nomo, la butono restas malŝaltita."
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
