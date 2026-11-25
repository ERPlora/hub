"""What the assistant does in each flow done on a screen, worked out from the manuals and the operation registry.

The operations of a flow are the ones whose row of a services table names it in its «Flujos» column; whether each one is
a tool of the assistant is what the registry says. The made-up manuals and operations below show each rule, and the
repository's own show that every flow done on a screen gets its answer.
"""

import re
from collections import Counter
from pathlib import Path

import pytest
from django.core.management import call_command
from live.operations import AI, INTERNAL, Operation, registry
from ninja import Schema

from base import qa_assistant, qa_coverage
from base.qa_assistant import Group
from base.qa_coverage import WorkbookFlow

REPO = Path(__file__).resolve().parents[2]
COUNTS = re.compile(r"^assistant: (\d+) can, (\d+) assistant only, (\d+) cannot, (\d+) undecided$")

MANUAL = """\
# Workbook — Ejemplo
Prefijo: SAMPLE

## Flujos

### SAMPLE-F01 Crear
Estado: hecho
Actor: responsable, asistente
Pantalla: Lista

### SAMPLE-F02 Consultar
Estado: hecho
Actor: empleado
Pantalla: Lista, Ficha

### SAMPLE-F03 Solo hablando
Estado: hecho
Actor: responsable, asistente
Pantalla: asistente

### SAMPLE-F04 Subir una foto
Estado: hecho
Actor: responsable, asistente
Pantalla: Ficha

### SAMPLE-F05 Nadie ha escrito qué operaciones usa
Estado: hecho
Actor: empleado
Pantalla: Ficha

### SAMPLE-F06 Lo hace el sistema
Estado: hecho
Actor: sistema
Pantalla: ninguna (se ve en la Lista)

### SAMPLE-F07 No hecho
Estado: no hecho
Actor: responsable, asistente
Pantalla: Lista

### SAMPLE-F08 Borrar
Estado: hecho
Actor: responsable
Pantalla: Ficha

## Servicios: lo que entra y lo que sale

### Lo que ofrece: consultas

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las cosas | ver | F01, F02 | `sample.item.list` |

## Para quien lo mantiene

### Lo que ofrece: acciones

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea una cosa | gestionar | F01, F03 | `sample.item.create` |
| Sube su foto | gestionar | F04 | `sample.item.upload` |
| Borra una cosa | gestionar | F08 | `sample.item.delete` |
| Cierra las de ayer | sistema | F06 | `sample.item.close` |
"""


def operation(name, *, kind="command", tool=True):
    return Operation(
        name=name,
        kind=kind,
        permission="sample.manage",
        input=Schema,
        output=Schema,
        expose_api=False,
        ai=AI(f"Does {name}.") if tool else INTERNAL,
        fn=lambda ctx, data: data,
    )


WRITE = operation("sample.item.create")
OTHER_WRITE = operation("sample.item.upload", tool=False)
READ = operation("sample.item.list", kind="query")
OTHER_READ = operation("sample.item.get", kind="query", tool=False)
PANEL = operation("base.assistant.turn", tool=False)
OPERATIONS = {
    op.name: op
    for op in (
        WRITE,
        OTHER_WRITE,
        READ,
        operation("sample.item.delete"),
        operation("sample.item.close"),
        operation("sample.item.rebuild"),
        operation("sample.item.archive", tool=False),
    )
}


def flow(*, actor="empleado", screen="Lista"):
    return WorkbookFlow("SAMPLE-F01", "sample", done=True, on_screen=True, actor=actor, screen=screen)


def manual(root, text, app="sample"):
    path = root / "apps" / app / "WORKBOOK.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return root


def cited(root, header, *rows):
    """The operations each flow cites in a manual whose only table has ``header`` and ``rows``."""
    table = "\n".join((header, "|---" * (header.count("|") - 1) + "|", *rows))
    return qa_assistant.cited_operations(manual(root, f"# Workbook\n\n### Servicios\n\n{table}\n"))


class TestTheOperationsOfAFlow:
    HEADER = "| Qué da | Quién puede | Flujos | Servicio |"

    def test_they_are_those_of_the_rows_that_name_it_in_the_order_written(self, tmp_path):
        assert cited(
            tmp_path,
            self.HEADER,
            "| Las cosas | ver | F01, F02 | `sample.item.list` |",
            "| Crea | gestionar | F02 | `sample.item.create`, `sample.item.check` |",
            "| Las cosas, otra vez | ver | F02 | `sample.item.list` |",
        ) == {
            "SAMPLE-F01": ("sample.item.list",),
            "SAMPLE-F02": ("sample.item.list", "sample.item.create", "sample.item.check"),
        }

    @pytest.mark.parametrize(
        ("header", "row"),
        [
            ("| Servicios | Flujos |", "| `sample.item.list` | F01 |"),
            ("| Operación | Qué da | Permiso | Flujos |", "| `sample.item.list` | Las cosas | ver | F01 |"),
            ("| Qué da | Flujos | En vivo | Servicio |", "| Las cosas | F01 | sí | `sample.item.list` |"),
        ],
        ids=["services", "operation", "another-column"],
    )
    def test_they_are_read_whatever_the_order_of_the_columns(self, tmp_path, header, row):
        assert cited(tmp_path, header, row) == {"SAMPLE-F01": ("sample.item.list",)}

    @pytest.mark.parametrize(
        ("header", "row"),
        [
            ("| Aviso de | Flujos | Servicio que escucha |", "| Ventas | F01 | `sale.sale.completed` |"),
            ("| Pieza | Flujos que la usan | Servicio |", "| El formulario | F01 | `sample.item.create` |"),
            ("| Qué da | Servicio |", "| Las cosas (F01) | `sample.item.list` |"),
        ],
        ids=["events", "shared-pieces", "no-flows"],
    )
    def test_a_table_without_both_columns_says_nothing(self, tmp_path, header, row):
        assert cited(tmp_path, header, row) == {}

    @pytest.mark.parametrize(
        ("flows", "ids"),
        [
            ("F01", ["SAMPLE-F01"]),
            ("F09–F11", ["SAMPLE-F09", "SAMPLE-F10", "SAMPLE-F11"]),
            ("F01, F99-F101", ["SAMPLE-F01", "SAMPLE-F99", "SAMPLE-F100", "SAMPLE-F101"]),
            ("F113, KITCHEN-F16, WHATSAPP_INBOX-F09", ["SAMPLE-F113", "KITCHEN-F16", "WHATSAPP_INBOX-F09"]),
            ("F97, en las tarjetas de Personal", ["SAMPLE-F97"]),
            ("ninguno: solo el asistente y la API", []),
            ("—", []),
        ],
    )
    def test_a_flow_is_named_by_its_number_its_id_or_a_range(self, tmp_path, flows, ids):
        assert list(cited(tmp_path, self.HEADER, f"| Algo | ver | {flows} | `sample.item.list` |")) == ids

    @pytest.mark.parametrize(
        ("services", "names"),
        [
            ("`sample.item.deactivate` / `.activate`", ["sample.item.deactivate", "sample.item.activate"]),
            (
                "`sample.tag.create`, `.update`; `.delete`",
                ["sample.tag.create", "sample.tag.update", "sample.tag.delete"],
            ),
            (
                "`sample.tag.create`, `.delete`, `sample.item.create`, `.delete`",
                ["sample.tag.create", "sample.tag.delete", "sample.item.create", "sample.item.delete"],
            ),
        ],
    )
    def test_a_name_that_starts_with_a_dot_takes_the_entity_of_the_one_before(self, tmp_path, services, names):
        assert cited(tmp_path, self.HEADER, f"| Algo | ver | F01 | {services} |") == {"SAMPLE-F01": tuple(names)}

    def test_a_pipe_written_inside_a_cell_does_not_move_the_columns(self, tmp_path):
        row = r"| Las cosas (a \| b) | ver | F01 | `sample.item.list` |"
        assert cited(tmp_path, self.HEADER, row) == {"SAMPLE-F01": ("sample.item.list",)}

    def test_every_manual_is_read_whole_and_a_flow_of_another_app_adds_up(self, tmp_path):
        manual(tmp_path, MANUAL)
        manual(tmp_path, "| Servicios | Flujos |\n|---|---|\n| `other.item.list` | SAMPLE-F01, F01 |\n", app="other")
        operations = qa_assistant.cited_operations(tmp_path)
        assert operations["OTHER-F01"] == ("other.item.list",)
        assert operations["SAMPLE-F01"] == ("other.item.list", "sample.item.list", "sample.item.create")
        assert operations["SAMPLE-F06"] == ("sample.item.close",)


class TestTheGroupOfAFlow:
    @pytest.mark.parametrize(
        ("operations", "group"),
        [
            ([WRITE], Group.CAN),
            ([WRITE, OTHER_WRITE, OTHER_READ], Group.CAN),
            ([READ], Group.CAN),
            ([READ, OTHER_READ], Group.CANNOT),
            ([OTHER_READ], Group.CANNOT),
            ([OTHER_WRITE], Group.CANNOT),
            ([OTHER_WRITE, READ], Group.CANNOT),
            ([], None),
        ],
        ids=[
            "a-write",
            "one-write-of-two",
            "only-reads",
            "a-read-of-two",
            "a-read-that-is-no-tool",
            "a-write-that-is-no-tool",
            "a-write-that-is-no-tool-and-a-read-that-is",
            "no-operation",
        ],
    )
    def test_it_comes_from_its_operations_when_it_has_another_screen(self, operations, group):
        assert qa_assistant.asked(flow(), operations).group == group

    def test_a_tool_never_used_from_the_chat_is_none(self):
        assert qa_assistant.asked(flow(), [operation("base.hub.reset")]).group == Group.CANNOT

    @pytest.mark.parametrize(
        "screen",
        [
            "asistente",
            "Asistente",
            "el asistente",
            "asistente o API",
            "asistente y API",
            "API; asistente",
            "asistente (en el chat)",
            "Tarjeta de confirmación del asistente",
        ],
    )
    @pytest.mark.parametrize("operations", [[WRITE], [READ], []], ids=["write", "read", "none"])
    def test_it_is_only_the_assistants_when_its_screen_is_no_other(self, screen, operations):
        assert qa_assistant.asked(flow(screen=screen), operations).group == Group.ASSISTANT_ONLY

    @pytest.mark.parametrize(
        "screen",
        [
            "Lista; asistente",
            "Lista, asistente",
            "Lista y asistente",
            "Lista o el asistente",
            "asistente; admin del Hub",
            "Bonos y paquetes, asistente",
            "Fichar (o el asistente)",
            "Pantalla (también el asistente: «marca lista la mesa 4»)",
            "Sala de asistentes",
            "API",
            "",
        ],
    )
    def test_it_is_not_only_the_assistants_with_another_screen(self, screen):
        assert qa_assistant.asked(flow(screen=screen), [WRITE]).group == Group.CAN

    def test_each_group_says_what_to_expect_and_the_one_that_cannot_which_screen_to_go_to(self):
        expected = {
            group: qa_assistant.asked(flow(screen=screen), operations).expected
            for group, screen, operations in (
                (Group.CAN, "Ficha", [WRITE]),
                (Group.ASSISTANT_ONLY, "asistente", [WRITE]),
                (Group.CANNOT, "Ficha {1}", [OTHER_WRITE]),
            )
        }
        assert len(set(expected.values())) == len(Group)
        assert "Ficha {1}" in expected[Group.CANNOT]
        assert "Ficha" not in expected[Group.CAN]


class TestWhetherAFlowContradictsItself:
    @pytest.mark.parametrize(
        ("actor", "screen", "operations", "contradicts"),
        [
            ("responsable, asistente", "Ficha", [WRITE], False),
            ("responsable, asistente", "Ficha", [READ], False),
            ("responsable, asistente", "Ficha", [OTHER_WRITE, READ], False),
            ("responsable, asistente", "Ficha", [OTHER_WRITE], True),
            ("responsable, asistente", "Ficha", [OTHER_READ], True),
            ("responsable, asistente", "Ficha", [], True),
            ("responsable; por el asistente, cualquiera", "Ficha", [OTHER_WRITE], True),
            ("responsable, asistente", "Asistente", [PANEL], True),
            ("los asistentes", "Ficha", [OTHER_WRITE], False),
            ("responsable", "Ficha", [WRITE, OTHER_WRITE], False),
            ("responsable", "Ficha", [OTHER_WRITE], False),
            ("responsable", "Ficha", [], False),
            ("responsable", "asistente", [WRITE], False),
            ("responsable", "asistente", [OTHER_WRITE, READ], False),
            ("responsable", "asistente", [OTHER_WRITE], True),
            ("responsable", "Ficha (también el asistente)", [OTHER_READ], True),
            ("responsable", "Ficha; asistente", [], False),
            ("responsable", "Asistente", [PANEL], False),
            ("responsable", "Asistente", [OTHER_READ, PANEL], False),
        ],
    )
    def test_it_does_when_it_names_the_assistant_and_no_tool_backs_it(self, actor, screen, operations, contradicts):
        assert qa_assistant.asked(flow(actor=actor, screen=screen), operations).contradicts is contradicts


class TestTheReport:
    @pytest.fixture
    def report(self, tmp_path):
        manual(tmp_path, MANUAL)
        return qa_assistant.report(tmp_path, qa_coverage.workbook_flows(tmp_path), OPERATIONS)

    def test_only_the_flows_done_on_a_screen_have_an_answer(self, report):
        assert {one.flow.id: one.group for one in report.flows} == {
            "SAMPLE-F01": Group.CAN,
            "SAMPLE-F02": Group.CAN,
            "SAMPLE-F03": Group.ASSISTANT_ONLY,
            "SAMPLE-F04": Group.CANNOT,
            "SAMPLE-F05": None,
            "SAMPLE-F08": Group.CAN,
        }

    def test_an_operation_the_registry_does_not_have_backs_nothing(self, tmp_path):
        manual(tmp_path, MANUAL)
        flows = qa_coverage.workbook_flows(tmp_path)
        report = qa_assistant.report(tmp_path, flows, {READ.name: READ})
        assert {one.flow.id: [op.name for op in one.operations] for one in report.flows} == {
            "SAMPLE-F01": [READ.name],
            "SAMPLE-F02": [READ.name],
            "SAMPLE-F03": [],
            "SAMPLE-F04": [],
            "SAMPLE-F05": [],
            "SAMPLE-F08": [],
        }

    def test_the_tools_no_flow_cites_leave_out_what_is_no_tool_and_what_a_flow_out_of_reach_cites(self, report):
        assert report.uncited_tools == ("sample.item.rebuild",)

    def test_a_tool_only_a_flow_of_no_manual_cites_is_cited_by_none(self, tmp_path):
        manual(tmp_path, MANUAL.replace("| F08 |", "| HUBS-F18 |"))
        report = qa_assistant.report(tmp_path, qa_coverage.workbook_flows(tmp_path), OPERATIONS)
        assert report.uncited_tools == ("sample.item.delete", "sample.item.rebuild")


class TestTheCommand:
    @pytest.fixture
    def lines(self, tmp_path, settings, monkeypatch, capsys):
        settings.BASE_DIR = manual(tmp_path, MANUAL)
        monkeypatch.setattr("base.management.commands.qa_coverage.registry", OPERATIONS)

        def run(**options):
            call_command("qa_coverage", **options)
            return capsys.readouterr().out.splitlines()

        return run

    def test_it_gives_each_flow_its_group_what_to_expect_and_its_operations_and_then_the_three_lists(self, lines):
        written = lines(assistant=True)
        assert written[written.index("assistant: 3 can, 1 assistant only, 1 cannot, 1 undecided") : -1] == [
            "assistant: 3 can, 1 assistant only, 1 cannot, 1 undecided",
            "  SAMPLE-F01 can: does it; check it on the screen or in the data"
            " — sample.item.list (tool), sample.item.create (tool)",
            "  SAMPLE-F02 can: does it; check it on the screen or in the data — sample.item.list (tool)",
            "  SAMPLE-F03 assistant only: does it, and there is no other way; check it on the screen or in the data"
            " — sample.item.create (tool)",
            "  SAMPLE-F04 cannot: says it does not do it and which screen does: Ficha — sample.item.upload",
            "  SAMPLE-F08 can: does it; check it on the screen or in the data — sample.item.delete (tool)",
            "undecided, none of their operations is known: 1",
            "  SAMPLE-F05",
            "contradictions, the assistant is named and no tool backs it: 1",
            "  SAMPLE-F04",
            "tools no flow cites: 1",
            "  sample.item.rebuild",
        ]
        assert written[-1].startswith("total: ")

    def test_without_the_option_it_says_nothing_about_the_assistant(self, lines):
        assert not any(line.startswith(("assistant:", "undecided", "contradictions", "tools")) for line in lines())


@pytest.fixture(scope="module")
def repo_flows():
    return qa_coverage.workbook_flows(REPO)


class TestTheRepository:
    @pytest.fixture
    def report(self, repo_flows):
        return qa_assistant.report(REPO, repo_flows, registry)

    def test_every_flow_done_on_a_screen_has_one_answer(self, report, repo_flows):
        assert [one.flow.id for one in report.flows] == [flow.id for flow in repo_flows.values() if flow.walkable]
        assert all(one.group is not None or not one.operations for one in report.flows)

    def test_every_group_has_flows_and_its_operations_are_in_the_registry(self, report):
        assert {one.group for one in report.flows} >= set(Group)
        assert all(registry[op.name] is op for one in report.flows for op in one.operations)

    def test_the_operations_written_short_are_read_whole(self):
        names = {name for operations in qa_assistant.cited_operations(REPO).values() for name in operations}
        assert not [name for name in names if name.startswith(".")]
        assert {"payment.method.activate", "customer.tag.delete", "table.hold.release"} <= names & registry.keys()

    def test_the_command_counts_the_flows_it_lists(self, capsys, repo_flows):
        call_command("qa_coverage", assistant=True)
        lines = capsys.readouterr().out.splitlines()
        stated = next(tuple(map(int, match.groups())) for line in lines if (match := COUNTS.match(line)))
        groups = Counter(
            group for line in lines for group in Group if re.match(rf"^  [A-Z][A-Z0-9_]*-F\d+ {group.value}: ", line)
        )
        assert stated[:3] == tuple(groups[group] for group in (Group.CAN, Group.ASSISTANT_ONLY, Group.CANNOT))
        assert sum(stated) == sum(flow.walkable for flow in repo_flows.values())
