"""Every Spanish WORKBOOK of the Hub has its English translation, made from its current customer's part.

The English file is the help an English reader gets in the app and what the store shows of a module.
``translate_workbooks --check`` looks only at the installed apps and lets a missing translation pass; this
walks the repository, so a module written down before its code has one too.
"""

from pathlib import Path

from base.catalog import WORKBOOK, WORKBOOK_EN, user_part, workbook_configs
from base.workbook_sections import current_body, marked

REPO = Path(__file__).resolve().parent.parent
SPANISH = "# Workbook — Cosas\n\n## Para qué sirve\n\nGuarda cosas.\n\n## Para quien lo mantiene\n\nNotas.\n"
ENGLISH_BODY = "## What it is for\n\nKeeps things.\n"


def spanish_workbooks() -> list[Path]:
    return sorted([REPO / "base" / WORKBOOK, *(REPO / "apps").glob(f"*/{WORKBOOK}")])


def translation_problem(spanish: Path) -> str | None:
    """``missing``, ``out of date`` or ``None`` when ``WORKBOOK.en.md`` carries the marks of the current Spanish part."""
    english = spanish.with_name(WORKBOOK_EN)
    if not english.is_file():
        return "missing"
    source = user_part(spanish.read_text(encoding="utf-8"))
    return "out of date" if current_body(source, english.read_text(encoding="utf-8")) is None else None


def test_a_translation_is_current_only_while_the_spanish_customers_part_is_unchanged(tmp_path):
    spanish = tmp_path / WORKBOOK
    spanish.write_text(SPANISH, encoding="utf-8")
    assert translation_problem(spanish) == "missing"

    (tmp_path / WORKBOOK_EN).write_text(marked(user_part(SPANISH), ENGLISH_BODY), encoding="utf-8")
    assert translation_problem(spanish) is None

    spanish.write_text(f"{SPANISH}Más notas para quien lo mantiene.\n", encoding="utf-8")
    assert translation_problem(spanish) is None

    spanish.write_text(SPANISH.replace("Guarda cosas.", "Guarda cosas y personas."), encoding="utf-8")
    assert translation_problem(spanish) == "out of date"


def test_every_workbook_of_the_hub_has_a_current_english_translation():
    found = spanish_workbooks()
    expected = {Path(config.path).resolve() / WORKBOOK for config in workbook_configs()}
    assert expected <= {path.resolve() for path in found}, "the scan missed a WORKBOOK"

    problems = {
        str(path.relative_to(REPO)): problem for path in found if (problem := translation_problem(path))
    }
    assert problems == {}
