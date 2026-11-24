"""A WORKBOOK holds only what serves today: the flows, rules and contracts that exist.

A dropped flow is deleted, not marked; a struck-through note, the comment saying where a section came from, a
comparison with the old product and the label of the piece of work or the dated review a rule came from are history,
and history lives in git, the pull requests and the plans. The scan reads every WORKBOOK of this repository, the
Spanish one and its English translation.
"""

import os
import re
from pathlib import Path

import pytest

from base.catalog import WORKBOOK, workbook_configs

REPO = Path(__file__).resolve().parent.parent
SKIPPED_FOLDERS = {"node_modules", "packages"}
WORKBOOK_NAME = re.compile(r"WORKBOOK(?:\.[a-z]{2})?\.md")

DROPPED = r"(?:descartad[oa]s?|discarded)\b"
# A name in backticks is a real file, test or screenshot (`APP-DEMO-<flow>-<width>.png`), not a label.
CODE_SPAN = re.compile(r"`[^`]*`")
RULES = (
    ("dropped flow", re.compile(rf"^\|\s*[A-Z][A-Z_]*-F\d+\s*\|.*\|\s*{DROPPED}[^|]*\|\s*$", re.IGNORECASE)),
    ("dropped flow", re.compile(rf"^(?:Estado|Status|State):\s*{DROPPED}", re.IGNORECASE)),
    ("struck-through text", re.compile(r"~~")),
    ("origin comment", re.compile(r"<!--\s*orig(?:en|in):", re.IGNORECASE)),
    (
        "old product",
        re.compile(r"\b(?:hub|saas|producto)s?\s+viejos?\b|\bold[\s-](?:hub|saas|product)s?\b", re.IGNORECASE),
    ),
    ("task label", re.compile(r"\b(?:FIX|CLOSE|MIG)-[A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)*|\bAPP-[A-Z][A-Z_]*-\d+\b")),
    (
        "dated review",
        re.compile(r"\b(?:revisi[oó]n|review)\s+(?:(?:del?|of|on)\s+)?20\d{2}-\d{2}-\d{2}", re.IGNORECASE),
    ),
)
OUTSIDE_CODE = {"task label"}

# A dash is escaped: written plainly, these samples would read as real labels to the scan of internal
# references in code.
FIX_LABEL = "FIX\x2dHUB-PRINTING-BELL-SILENT"
APP_LABEL = "APP\x2dBASE-5"
SCREENSHOT = "APP\x2dBASE-10-BASE\x2dG152"
DEMO_SCREENSHOT = "APP\x2dDEMO-CLOSE-DEMO"


def violations(text: str) -> list[tuple[int, str, str]]:
    """Each line of ``text`` that keeps history, as (line number, rule, line)."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        prose = CODE_SPAN.sub("", line)
        found += [
            (number, rule, line.strip())
            for rule, pattern in RULES
            if pattern.search(prose if rule in OUTSIDE_CODE else line)
        ]
    return found


def workbooks(root: Path) -> list[Path]:
    """Every WORKBOOK under ``root``, leaving out dependencies, submodules and hidden folders."""
    found = []
    for folder, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in SKIPPED_FOLDERS and not name.startswith(".")]
        found += [Path(folder) / name for name in files if WORKBOOK_NAME.fullmatch(name)]
    return sorted(found)


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("| SALE-F36 | Cobrar desde otra caja | descartado |", "dropped flow"),
        ("| KITCHEN-F30 | Print the ticket twice | discarded |", "dropped flow"),
        ("Estado: descartado — nadie lo usaba.", "dropped flow"),
        ("Status: discarded — nobody used it.", "dropped flow"),
        ("~~El ticket caducaba en un día~~ — cerrada (antes).", "struck-through text"),
        ("<!-- origen: copiado tal cual -->", "origin comment"),
        ("<!-- origin: copied as it was -->", "origin comment"),
        ("Igual que en el hub viejo, la lista se ordena por fecha.", "old product"),
        ("El SaaS viejo pedía la clave dos veces.", "old product"),
        ("Lo que el Producto Viejo guardaba.", "old product"),
        ("Like the old Hub, it asks twice.", "old product"),
        ("Like the old SaaS, it asks twice.", "old product"),
        ("ERPlora's old product kept the keys.", "old product"),
        (f"- **Presencia** ({FIX_LABEL}): el aviso suena.", "task label"),
        ("Reservas online cierra con CLOSE-ONLINE_BOOKING.", "task label"),
        (f"- Personas y permisos ({APP_LABEL}): las personas son `Membership`.", "task label"),
        ("- **En persona** (`ai.in_person`, revisión 2026-10-30): sentar a la mesa.", "dated review"),
        ("- **In person** (review of 2026-10-30): seat a table.", "dated review"),
    ],
)
def test_each_kind_of_history_is_caught(text, rule):
    assert violations(f"## Flujos\n\n{text}\n") == [(3, rule, text)]


def test_what_describes_the_product_of_today_is_left_alone():
    text = f"""<!-- from WORKBOOK.md sha256:000000000000 -->
| SALE-F12 | Llegar a una dirección retirada | hecho |
| INVOICE-F03 | Descartado: vaciar la papelera | hecho |
Estado: hecho
Estado de la app: completa
El aviso dice «Descartado.» y la fila desaparece.
Un dispositivo retirado no vuelve a imprimir.
Descartar un borrador no deja rastro.
One of a number nobody has connected is discarded.
El hub vuelve a abrir el ticket viejo del cliente.
Implicados: HUB_APP-F30 (ERPlora/app), BASE-F35, VERIFACTU-F05.
Las capturas se llaman `{SCREENSHOT}-<idioma>-<pantalla>-<ancho>` y `{DEMO_SCREENSHOT}-*`.
La e2e `tests/e2e/fix-hub-spa-static-probes.spec.ts` lo prueba en los 3 tamaños.
La serie numera FAC-2026-000001 y la siguiente, FAC-2026-000002.
La revisión del informe no promete lo que no se enciende.
"""

    assert violations(text) == []


def test_the_workbooks_of_this_repository_keep_no_history():
    found = workbooks(REPO)
    expected = {Path(config.path).resolve() / WORKBOOK for config in workbook_configs()}
    assert expected <= {path.resolve() for path in found}, "the scan missed a WORKBOOK"

    history = [
        f"{path.relative_to(REPO)}:{number}: {rule}: {line}"
        for path in found
        for number, rule, line in violations(path.read_text(encoding="utf-8"))
    ]
    assert history == [], "\n".join(history)


def test_the_walk_skips_dependencies_and_submodules(tmp_path):
    for place in ("apps/sale", "node_modules/x", "packages/live", ".venv/lib"):
        (tmp_path / place).mkdir(parents=True)
        (tmp_path / place / "WORKBOOK.md").write_text("~~x~~\n", encoding="utf-8")
    (tmp_path / "apps/sale" / "WORKBOOK.en.md").write_text("ok\n", encoding="utf-8")
    (tmp_path / "apps/sale" / "README.md").write_text("ok\n", encoding="utf-8")

    assert workbooks(tmp_path) == [tmp_path / "apps/sale" / "WORKBOOK.en.md", tmp_path / "apps/sale" / "WORKBOOK.md"]
