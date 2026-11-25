"""base/catalog/workbooks.py: the customer's part of a WORKBOOK and the state of its translations.

The last tests run it on the real modules: the check of CI.
"""

import pytest

from base.catalog.errors import WorkbookError
from base.catalog.workbooks import stale_translations, user_part
from base.tests.apps_on_disk import CUT, NOT_CLOSING, OLD_PART, ORIGIN, USER_PART, WORKBOOK, by_hand, module, translated


def test_user_part_runs_from_the_first_section_to_the_maintainers_heading():
    assert user_part(WORKBOOK) == USER_PART


def test_user_part_drops_the_title_and_the_header():
    part = user_part(WORKBOOK)
    for line in (
        "# Workbook",
        "Prefijo:",
        "Alcance MVP:",
        "Estado de la app:",
        "> Manual de usuario",
    ):
        assert line not in part
    # The flows' «Estado:» lines are published as they are: only the HTML comments go.
    assert "Estado: hecho" in part


def test_user_part_does_not_cut_before_the_exact_heading():
    text = WORKBOOK.replace(
        "## Cómo se usa\n",
        "## Cómo se usa\n\nPara quien lo mantiene, nada.\n\n## Para quien lo mantiene la tienda\n",
    )
    part = user_part(
        text.replace("(#cómo-se-usa)", "(#para-quien-lo-mantiene-la-tienda)")
    )
    assert "## Para quien lo mantiene la tienda" in part
    assert "Notas internas" not in part


def test_user_part_fails_without_the_maintainers_heading():
    with pytest.raises(WorkbookError, match="Para quien lo mantiene"):
        user_part(WORKBOOK.replace(CUT, "## Notas"))


def test_user_part_fails_when_nothing_is_above_the_heading():
    with pytest.raises(WorkbookError, match="nothing"):
        user_part(f"# Workbook\n\n{CUT}\n\n- Notas.\n")


def test_the_heading_inside_a_code_block_does_not_cut():
    fenced = WORKBOOK.replace(
        "### Paso a paso\n",
        f"### Paso a paso\n\n```markdown\n{CUT}\n```\n\n~~~\n{CUT}\n~~~\n",
    )
    part = user_part(fenced)
    assert part.count(CUT) == 2
    assert "Estado: hecho" in part
    assert "Notas internas" not in part


@pytest.mark.parametrize(("fence", "inner"), NOT_CLOSING.values(), ids=NOT_CLOSING)
def test_only_a_fence_like_the_opening_one_closes_its_code_block(fence, inner):
    fenced = WORKBOOK.replace("### Paso a paso\n", f"### Paso a paso\n\n{fence}\n{inner}\n{CUT}\n{fence}\n")
    part = user_part(fenced)
    assert CUT in part
    assert "Estado: hecho" in part


def test_a_dangling_anchor_fails_and_names_it():
    with pytest.raises(WorkbookError, match="#no-existe"):
        user_part(WORKBOOK.replace("(#cómo-se-usa)", "(#no-existe)"))


def test_an_anchor_to_a_heading_the_cut_leaves_out_fails():
    with pytest.raises(WorkbookError, match="#cambios-frente-al-producto-actual"):
        user_part(
            WORKBOOK.replace("(#cómo-se-usa)", "(#cambios-frente-al-producto-actual)")
        )


@pytest.mark.parametrize(
    ("text", "commented"),
    [
        # On a line of its own, under a flow's title: the line goes with it.
        ("### Paso a paso\n", f"### Paso a paso\n{ORIGIN}\n"),
        # Between blank lines, over several lines: no blank line is doubled.
        (
            "## Cómo se usa\n\n",
            "## Cómo se usa\n\n<!-- código:\n  https://example.com/a.py\n-->\n\n",
        ),
        # Inside a line: the text around it is joined by one space, as it reads.
        ("**cosas**. Ver", "**cosas**. <!-- código: https://example.com/a.py --> Ver"),
        ("**cosas**. Ver", "**cosas**. <!-- a --> Ver<!-- b -->"),
        # Closed before the text of a line.
        ("### Paso a paso\n", "### Paso a paso\n<!-- origen:\n  old-hub:HUB-F212 --> "),
        # At the end of a line, and opened there to close lines below.
        ("list.png)\n", "list.png) <!-- código: https://example.com/a.py -->\n"),
        ("list.png)\n", "list.png) <!-- código:\n  https://example.com/a.py\n-->\n"),
    ],
)
def test_user_part_leaves_out_the_html_comments(text, commented):
    assert WORKBOOK.count(text) == 1
    assert user_part(WORKBOOK.replace(text, commented)) == USER_PART


def test_a_comment_inside_a_code_block_is_published_as_it_is():
    blocks = f"```html\n{ORIGIN}\n```\n\n~~~\n<!-- varias\nlíneas -->\n~~~\n"
    part = user_part(WORKBOOK.replace("Estado: hecho\n", f"Estado: hecho\n\n{blocks}"))
    assert part == f"{USER_PART}\n{blocks}"


def test_inside_a_comment_the_heading_does_not_cut_nor_a_fence_open_a_block():
    hidden = f"### Paso a paso\n<!--\n{CUT}\n```\n-->\n"
    assert user_part(WORKBOOK.replace("### Paso a paso\n", hidden)) == USER_PART


def test_a_comment_that_never_closes_fails_naming_its_line():
    # Line 17 of WORKBOOK, right under «### Paso a paso».
    unclosed = WORKBOOK.replace("### Paso a paso\n", "### Paso a paso\n<!-- origen:\n")
    with pytest.raises(WorkbookError, match=r"\b17\b"):
        user_part(unclosed)


def test_a_comment_left_open_below_the_cut_is_never_read():
    assert user_part(f"{WORKBOOK}\nAbre un comentario con `<!--`.\n") == USER_PART


def test_stale_translations_lists_the_modules_to_translate_again(tmp_path):
    configs = [
        module(tmp_path, "current", en=translated(USER_PART)),
        module(tmp_path, "stale", en=translated(OLD_PART)),
        module(tmp_path, "untranslated"),
    ]
    assert stale_translations(configs) == {"stale": by_hand("## Para qué sirve")}


def test_a_workbook_that_cannot_be_read_is_told_once_by_the_registry_for_a_module(tmp_path):
    broken = WORKBOOK.replace("(#cómo-se-usa)", "(#no-existe)")
    things, base = module(tmp_path, workbook=broken), module(tmp_path, "base", kind="platform", workbook=broken)
    assert stale_translations([things]) == {}
    assert stale_translations([base]) == {"base": "WORKBOOK.md: links to no heading of the published part: #no-existe."}


def test_no_real_translation_is_stale():
    stale = stale_translations()
    assert stale == {}, "\n".join(f"{label}: {what_to_do}" for label, what_to_do in stale.items())
