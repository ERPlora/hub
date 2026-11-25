"""base/catalog/app_registry.py: ``build_registry`` reads every module's metadata, catalogue, baked
icon and documentation without touching a database or the network, gathering one error per
rule. The last test runs it on the real modules: the check of CI.
"""

import hashlib

import pytest
from django.utils.translation import pgettext_lazy

from base.catalog.app_registry import AppEntry, build_registry
from base.catalog.errors import RegistryError
from base.catalog.workbooks import source_hash
from base.tests.apps_on_disk import (
    CUT,
    ENGLISH,
    ICONS,
    OLD_PART,
    ORIGIN,
    SPANISH,
    SYMLINKS,
    USER_PART,
    WORKBOOK,
    by_hand,
    linked_module,
    module,
    problems,
    translated,
)


def test_a_module_becomes_one_entry_with_both_languages_its_icon_and_its_documentation(
    tmp_path,
):
    config = module(
        tmp_path,
        en=translated(USER_PART),
        requires=["stock", "catalog"],
        verticals=["restaurant", "hair_salon"],
        premium=True,
        images=("docs/img/list.png",),
    )

    [entry] = build_registry([config], icons=ICONS)

    assert entry == AppEntry(
        id="things",
        name_en="Things",
        name_es="Cosas",
        summary_en="Keep your things.",
        summary_es="Guarda tus cosas.",
        description_en="Every thing in one place.",
        description_es="Cada cosa en su sitio.",
        icon="ion:cube-outline",
        icon_svg=ICONS["ion:cube-outline"],
        category="catalog",
        premium=True,
        requires=["catalog", "stock"],
        verticals=["hair_salon", "restaurant"],
        listed=True,
        docs={"es": USER_PART, "en": ENGLISH},
    )


def test_without_a_translation_there_is_no_english_document(tmp_path):
    [entry] = build_registry([module(tmp_path)], icons=ICONS)
    assert entry.docs == {"es": USER_PART}


def test_the_documentation_is_registered_without_the_workbooks_comments(tmp_path):
    commented = WORKBOOK.replace("### Paso a paso\n", f"### Paso a paso\n{ORIGIN}\n")
    [entry] = build_registry([module(tmp_path, workbook=commented)], icons=ICONS)
    assert entry.docs == {"es": USER_PART}


def test_a_comment_does_not_make_the_translation_stale(tmp_path):
    # Tying a flow to its origin is no change for the customer: nothing to translate again.
    commented = WORKBOOK.replace("### Paso a paso\n", f"### Paso a paso\n{ORIGIN}\n")
    config = module(tmp_path, workbook=commented, en=translated(USER_PART))
    [entry] = build_registry([config], icons=ICONS)
    assert set(entry.docs) == {"es", "en"}


def test_a_text_without_its_spanish_msgstr_fails_naming_the_app_and_the_field(tmp_path):
    spanish = {
        key: value for key, value in SPANISH.items() if key != "Keep your things."
    }
    [problem] = problems([module(tmp_path, spanish=spanish)])
    assert problem.startswith("things: summary:")
    assert "msgstr" in problem and "compilemessages" in problem


def test_a_name_that_is_the_same_in_both_languages_still_needs_its_msgstr(tmp_path):
    assert build_registry(
        [module(tmp_path, verbose_name="Demo", spanish={**SPANISH, "Demo": "Demo"})],
        icons=ICONS,
    )
    [problem] = problems([module(tmp_path / "other", verbose_name="Demo")])
    assert problem.startswith("things: verbose_name:")


def test_a_name_said_with_a_context_is_read_with_its_context(tmp_path):
    """A module says its name with ``pgettext_lazy`` when an earlier app translates the same English otherwise (Página
    web's «Website» against Clientes' «Web», hub#661): its catalogue keeps only that entry, which is the one the store
    reads, as Django does."""
    spanish = {key: value for key, value in SPANISH.items() if key != "Things"}
    config = module(
        tmp_path,
        verbose_name=pgettext_lazy("app name", "Things"),
        spanish={**spanish, "app name\x04Things": "Cosas"},
    )
    [entry] = build_registry([config], icons=ICONS)
    assert (entry.name_en, entry.name_es) == ("Things", "Cosas")


def test_a_plain_entry_does_not_speak_for_a_name_said_with_a_context(tmp_path):
    # Django never falls back from a context to the plain entry: neither does the store, or a typo in the context
    # would register a Spanish that no screen shows.
    config = module(tmp_path, verbose_name=pgettext_lazy("app name", "Things"))
    [problem] = problems([config])
    assert problem.startswith("things: verbose_name:") and "'app name'" in problem


def test_a_spanish_text_longer_than_its_column_fails(tmp_path):
    spanish = {**SPANISH, "Keep your things.": "x" * 121}
    [problem] = problems([module(tmp_path, spanish=spanish)])
    assert problem.startswith("things: summary:") and "120" in problem


def test_an_english_text_longer_than_its_column_fails_too(tmp_path):
    # live.E007 checks it in `manage.py check`; register_apps() also runs where no check ran (the worker).
    name = "N" * 81
    [problem] = problems(
        [module(tmp_path, verbose_name=name, spanish={**SPANISH, name: "Cosas"})]
    )
    assert (
        problem.startswith("things: verbose_name:")
        and "English" in problem
        and "80" in problem
    )


def test_an_icon_that_is_not_baked_fails_with_the_command_that_bakes_it(tmp_path):
    [problem] = problems([module(tmp_path, icon="lucide:box")])
    assert problem.startswith("things: icon:")
    assert "lucide:box" in problem and "pnpm gen:app-icons" in problem


def test_a_workbook_without_the_maintainers_heading_fails(tmp_path):
    [problem] = problems([module(tmp_path, workbook=WORKBOOK.replace(CUT, "## Notas"))])
    assert problem.startswith("things: WORKBOOK.md:")
    assert "Para quien lo mantiene" in problem


def test_a_module_without_workbook_fails(tmp_path):
    [problem] = problems([module(tmp_path, workbook=None)])
    assert problem.startswith("things: WORKBOOK.md:")


def test_a_stale_translation_fails_telling_to_translate_by_hand_only_the_sections_left_behind(tmp_path):
    """ERPlora uses no ANTHROPIC_API_KEY: never a command that calls the API."""
    [problem] = problems([module(tmp_path, en=translated(OLD_PART))])
    assert problem == f"things: WORKBOOK.en.md: out of date with WORKBOOK.md: {by_hand('## Para qué sirve')}"
    assert "translate_workbooks" not in problem


def test_a_translation_without_its_marks_is_stale_in_every_section(tmp_path):
    [problem] = problems([module(tmp_path, en=ENGLISH)])
    every = by_hand("## Para qué sirve", "## Cómo se usa", "### Paso a paso")
    assert problem == f"things: WORKBOOK.en.md: out of date with WORKBOOK.md: {every}"


def test_a_translation_with_one_heading_more_is_stale_though_no_section_is_behind(tmp_path):
    [problem] = problems([module(tmp_path, en=f"{translated(USER_PART)}\n## More\n")])
    assert problem.endswith(": no section is missing: a heading or its mark is out of place")


def test_a_translation_with_a_dangling_anchor_fails(tmp_path):
    en = translated(USER_PART, ENGLISH.replace("(#how-to-use-it)", "(#nowhere)"))
    [problem] = problems([module(tmp_path, en=en)])
    assert problem.startswith("things: WORKBOOK.en.md:") and "#nowhere" in problem


@pytest.mark.parametrize(
    "image", ["docs/img/diagram.svg", "docs/img/sub/notes.txt", "docs/img/photo.bmp"]
)
def test_an_image_with_another_extension_fails(tmp_path, image):
    [problem] = problems([module(tmp_path, images=("docs/img/list.png", image))])
    assert problem.startswith("things: docs/img:")
    assert image.removeprefix("docs/img/") in problem


def test_allowed_images_hidden_files_and_files_outside_docs_img_pass(tmp_path):
    images = (
        "docs/img/a.png",
        "docs/img/b.JPG",
        "docs/img/c.jpeg",
        "docs/img/d.webp",
        "docs/img/sub/e.gif",
    )
    others = ("docs/img/.DS_Store", "docs/notes.txt", "docs/diagram.svg")
    assert build_registry([module(tmp_path, images=images + others)], icons=ICONS)


def test_only_modules_are_registered(tmp_path):
    platform = module(tmp_path, "base", kind="platform")
    entries = build_registry([platform, module(tmp_path, "things")], icons=ICONS)
    assert [entry.id for entry in entries] == ["things"]


def test_the_order_is_by_label_whatever_the_order_of_the_apps(tmp_path):
    configs = [module(tmp_path, label) for label in ("zeta", "alpha", "mid")]
    assert [entry.id for entry in build_registry(configs, icons=ICONS)] == [
        "alpha",
        "mid",
        "zeta",
    ]


def test_every_problem_of_every_module_is_gathered(tmp_path):
    broken = [
        module(tmp_path, "beta", icon="lucide:box", workbook=None),
        module(tmp_path, "alpha", spanish={}),
    ]
    found = problems(broken)
    assert [problem.split(":")[0] for problem in found] == [
        "alpha",
        "alpha",
        "alpha",
        "beta",
        "beta",
    ]
    assert str(RegistryError(found)).count("\n") == len(found)


def test_the_baked_icons_are_read_from_the_generated_json(tmp_path, settings):
    settings.BASE_DIR = tmp_path
    (tmp_path / "frontend" / "generated").mkdir(parents=True)
    (tmp_path / "frontend" / "generated" / "app-icons.json").write_text(
        '{"ion:cube-outline": "<svg/>"}'
    )
    [entry] = build_registry([module(tmp_path / "apps")])
    assert entry.icon_svg == "<svg/>"


def test_without_the_generated_json_every_icon_fails(tmp_path, settings):
    settings.BASE_DIR = tmp_path
    [problem] = problems([module(tmp_path / "apps")], icons=None)
    assert "pnpm gen:app-icons" in problem


@pytest.mark.parametrize(("path", "target", "static"), SYMLINKS)
def test_a_symbolic_link_fails_the_registry_naming_the_app_and_the_link(
    tmp_path, path, target, static
):
    [problem] = problems([linked_module(tmp_path, path, target)])

    assert problem.startswith("things: docs/img:")
    assert "symbolic link" in problem
    assert f"replace {path} " in problem


def test_the_real_modules_build_their_registry():
    entries = build_registry()
    demo = next(entry for entry in entries if entry.id == "demo")
    assert (demo.name_en, demo.name_es) == ("Demo", "Demo")
    assert demo.listed is False
    assert demo.icon_svg.startswith("<svg")
    assert demo.docs["es"].startswith("## ")
    assert hashlib.sha256(demo.docs["es"].encode()).hexdigest() == source_hash(
        demo.docs["es"]
    )
