"""Guardrail of «only mine or all»: a model whose rows belong to someone is read through its ``Owned`` declaration.

An app declares in ``apps/<app>/queries/ownership.py`` whose each row of a model is (``base.queries.ownership.Owned``),
and its reads go through ``<DECLARATION>.visible(ctx)`` (its figures, through ``<DECLARATION>.counted(ctx)``): a person
without the «see all» permission gets only theirs.
``<Model>.objects`` in a ``queries`` door skips that, so here every such read is in :data:`UNSCOPED_READS`, closed and
with its reason; what the list names must still be there, so it never rots; and a planted read is caught, so a scan
that found nothing is never taken for a clean tree.
"""

import ast
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from orm_doors import is_door

REPO = Path(__file__).resolve().parent.parent
#: Attributes that are a model's manager: ``Model.objects…`` is always the ORM.
MANAGERS = frozenset({"objects", "_default_manager", "_base_manager"})
#: Where an app declares whose its rows are.
DECLARATIONS = "apps/*/queries/ownership.py"

# ── Why a read may skip the declaration ──────────────────────────────────────────────────────────────────────────────

#: Another app's write names the record by its id: who may do it is that write's own permission.
OTHER_APPS_WRITE = "another app's write"
#: Nobody reads a row: a count or a yes/no about the whole table.
NO_ROW_READ = "no row read"
#: The record of a check, a table or a register session being worked on, not the history of sales.
PART_OF_THE_WORK = "part of the work at hand"
#: A customer's public page, by the signed code printed on their own paper.
PUBLIC_BY_CODE = "public, by its code"
#: A record reached through another the caller already sees by its declaration: a document's links, a sale's document.
REACHED_THROUGH = "reached through one the caller sees"
#: The numbering of a whole series, which a gap or the book of numbers is: numbers, never a customer or an amount.
WHOLE_SERIES = "the whole series"
#: Only the platform runs it: no person is ever the caller.
ONLY_THE_SYSTEM = "only the system"

#: Every read of an owned model in a ``queries`` door that skips its declaration: ``(path, function) → (kind, why)``.
UNSCOPED_READS: dict[tuple[str, str], tuple[str, str]] = {
    ("apps/sale/queries/sales.py", "find_sale"): (
        OTHER_APPS_WRITE,
        "Invoicing issues and rectifies the documents of the sale a charge, a void or a refund gives it, and Services "
        "names the sale that paid for a voucher; Sales' own reads and commands look a sale up with visible_sale.",
    ),
    ("apps/sale/queries/sales.py", "keeps_fiscal_documents"): (
        NO_ROW_READ,
        "Whether the business's database holds any sale at all, which the platform asks before a database can go.",
    ),
    ("apps/sale/queries/checkout.py", "operation_total"): (
        PART_OF_THE_WORK,
        "What the check being charged already charged in parts, for the cash limit of the whole operation.",
    ),
    ("apps/sale/queries/receipt_codes.py", "sale_of_code"): (
        PUBLIC_BY_CODE,
        "The page where the customer asks for the full invoice of their ticket, opened by the code signed on it.",
    ),
    ("apps/cash_register/queries/lines.py", "sale_lines"): (
        PART_OF_THE_WORK,
        "The tenders of the sales charged and voided while a register session was open: the session's takings.",
    ),
    ("apps/cash_register/queries/unassigned.py", "unassigned_totals"): (
        PART_OF_THE_WORK,
        "How many sale tenders and comps of a time window no register session copied, counted for the drawer.",
    ),
    ("apps/table/queries/__init__.py", "sessions_now"): (
        PART_OF_THE_WORK,
        "What the check of each table of the room charged, to say whether it is paid.",
    ),
    ("apps/invoice/queries/__init__.py", "with_links"): (
        NO_ROW_READ,
        "Whether each document of a list the caller sees was replaced by a full invoice.",
    ),
    ("apps/invoice/queries/__init__.py", "_loaded"): (
        REACHED_THROUGH,
        "The document the caller opened, read again with the documents it rectifies, replaces or is rectified by, "
        "which its detail names as links.",
    ),
    ("apps/invoice/queries/__init__.py", "invoice_detail"): (
        REACHED_THROUGH,
        "The full invoice that replaced the ticket the caller opened, which its detail names as a link.",
    ),
    ("apps/invoice/queries/__init__.py", "document_of_sale"): (
        REACHED_THROUGH,
        "The document of a sale the caller reached through its declaration (by_source looks it up with "
        "visible_sale), and the one Sales' void and refund rectify.",
    ),
    ("apps/invoice/queries/__init__.py", "series_started"): (
        NO_ROW_READ,
        "Whether a series numbered any document, which freezes its prefix, format and next number.",
    ),
    ("apps/invoice/queries/__init__.py", "list_series"): (
        NO_ROW_READ,
        "Whether each listed series numbered any document.",
    ),
    ("apps/invoice/queries/__init__.py", "rectifiable"): (
        NO_ROW_READ,
        "Whether a ticket was already replaced by a full invoice, which is then the one to rectify.",
    ),
    ("apps/invoice/queries/__init__.py", "numbering_gaps"): (
        WHOLE_SERIES,
        "The gaps of a series' numbering, which only the whole series can tell.",
    ),
    ("apps/invoice/queries/__init__.py", "allocations"): (
        WHOLE_SERIES,
        "The book of numbers handed out in a series, with the type and date of each document.",
    ),
    ("apps/invoice/queries/__init__.py", "find_platform_invoice"): (
        ONLY_THE_SYSTEM,
        "ERPlora's own invoices on its platform hub, which the SaaS issues and asks about by their reference.",
    ),
    ("apps/invoice/queries/fiscal_archive.py", "keeps_fiscal_documents"): (
        NO_ROW_READ,
        "Whether the business's database holds any invoice at all, which the platform asks before a database can go.",
    ),
    ("apps/invoice/queries/fiscal_archive.py", "invoices"): (
        ONLY_THE_SYSTEM,
        "Every invoice of a business that left, for the fiscal archive the platform keeps of it.",
    ),
    ("apps/invoice/queries/public.py", "ticket_of_code"): (
        PUBLIC_BY_CODE,
        "The page where the customer asks for the full invoice of their ticket, opened by the code signed on it.",
    ),
    ("apps/invoice/queries/public.py", "public_ticket"): (
        PUBLIC_BY_CODE,
        "The ticket that code opens and, once issued, its full invoice, shown on that same page.",
    ),
    ("apps/verifactu/queries/records.py", "find_invoice"): (
        OTHER_APPS_WRITE,
        "VeriFactu seals or corrects the record of the document it is given (and of its test invoice); who may is "
        "VeriFactu's own permission.",
    ),
}


def owned_models(root: Path) -> dict[str, str]:
    """``{model: app}`` of every ``Owned(<Model>, …)`` declared at the top of an app's ``queries/ownership.py``."""
    found: dict[str, str] = {}
    for path in sorted(root.glob(DECLARATIONS)):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and _called(node.func) == "Owned" and node.args:
                model = node.args[0]
                if isinstance(model, ast.Name):
                    found[model.id] = path.parent.parent.name
    return found


def _called(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else None


def query_doors(root: Path) -> Iterator[PurePosixPath]:
    """Every read door of the apps: ``apps/<app>/queries.py`` and the modules of ``apps/<app>/queries/``."""
    for path in sorted((root / "apps").rglob("*.py")):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        if "tests" not in relative.parts and is_door(relative) and "queries" in (relative.stem, relative.parent.name):
            yield relative


def local_names(tree: ast.Module, path: PurePosixPath, models: dict[str, str]) -> dict[str, str]:
    """``{name in this file: owned model}`` for each owned model this file imports from its app's models."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            app = models.get(alias.name)
            if app is not None and _from_models_of(node, app, path):
                names[alias.asname or alias.name] = alias.name
    return names


def _from_models_of(node: ast.ImportFrom, app: str, path: PurePosixPath) -> bool:
    if node.level == 0:
        return node.module == f"apps.{app}.models"
    return node.module == "models" and path.parts[:2] == ("apps", app)


class _Reads(ast.NodeVisitor):
    """``(function, model)`` of every ``<Model>.objects`` of an owned model, by the function it is in."""

    def __init__(self, names: dict[str, str]) -> None:
        self.names = names
        self.stack: list[str] = []
        self.found: list[tuple[str, str]] = []

    def _in_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _in_function
    visit_AsyncFunctionDef = _in_function

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in MANAGERS and isinstance(node.value, ast.Name) and node.value.id in self.names:
            self.found.append((self.stack[-1] if self.stack else "<module>", self.names[node.value.id]))
        self.generic_visit(node)


def unscoped_reads(root: Path) -> set[tuple[str, str]]:
    """``(path, function)`` of every read of an owned model in a ``queries`` door that skips its declaration."""
    models = owned_models(root)
    found: set[tuple[str, str]] = set()
    for path in query_doors(root):
        tree = ast.parse((root / path).read_text(encoding="utf-8"))
        names = local_names(tree, path, models)
        if not names:
            continue
        reads = _Reads(names)
        reads.visit(tree)
        found |= {(str(path), function) for function, _model in reads.found}
    return found


# ── The tree as it is ────────────────────────────────────────────────────────────────────────────────────────────────


def test_the_declarations_are_found():
    found = owned_models(REPO)
    assert (found["Sale"], found["VoucherSession"]) == ("sale", "sale")
    assert found["Invoice"] == "invoice"


def test_every_read_of_an_owned_model_goes_through_its_declaration_or_is_listed_with_its_reason():
    skipped = unscoped_reads(REPO) - set(UNSCOPED_READS)
    assert skipped == set(), (
        f"{sorted(skipped)} read an owned model with <Model>.objects: read it with <DECLARATION>.visible(ctx) (a "
        "figure with <DECLARATION>.counted(ctx); visible_sale in Sales), or add it to UNSCOPED_READS with a reason a "
        "reviewer can weigh"
    )


def test_what_the_list_names_still_reads_without_the_declaration():
    gone = set(UNSCOPED_READS) - unscoped_reads(REPO)
    assert gone == set(), f"{sorted(gone)} no longer read an owned model by hand: take them off UNSCOPED_READS"


def test_every_reason_is_one_of_the_kinds_and_says_why():
    kinds = {
        OTHER_APPS_WRITE,
        NO_ROW_READ,
        PART_OF_THE_WORK,
        PUBLIC_BY_CODE,
        REACHED_THROUGH,
        WHOLE_SERIES,
        ONLY_THE_SYSTEM,
    }
    for read, (kind, why) in UNSCOPED_READS.items():
        assert kind in kinds and why.endswith("."), read


# ── A planted read is caught ─────────────────────────────────────────────────────────────────────────────────────────

DECLARED = "from apps.sale.models import Sale\nfrom base.queries.ownership import Owned\n\nSALES = Owned(Sale)\n"


def tree_with(tmp_path: Path, files: dict[str, str]) -> Path:
    for path, source in {"apps/sale/queries/ownership.py": DECLARED, **files}.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(source, encoding="utf-8")
    return tmp_path


def test_a_planted_read_in_a_queries_module_is_caught(tmp_path):
    peek = "from apps.sale.models import Sale\n\n\ndef peek():\n    return Sale.objects.all()\n"
    root = tree_with(tmp_path, {"apps/sale/queries/peek.py": peek})
    assert unscoped_reads(root) == {("apps/sale/queries/peek.py", "peek")}


def test_a_read_under_another_name_in_another_apps_queries_file_is_caught(tmp_path):
    peek = "from apps.sale.models import Sale as Charged\n\n\ndef peek():\n    return Charged.objects.first()\n"
    relative = "from ..models import Sale\n\n\ndef peek():\n    return Sale._default_manager.all()\n"
    root = tree_with(tmp_path, {"apps/shop/queries.py": peek, "apps/sale/queries/other.py": relative})
    assert unscoped_reads(root) == {("apps/shop/queries.py", "peek"), ("apps/sale/queries/other.py", "peek")}


def test_a_planted_read_of_an_invoice_is_caught(tmp_path):
    declared = "from apps.invoice.models import Invoice\nfrom base.queries.ownership import Owned\n\nINVOICES = Owned(Invoice)\n"
    peek = "from ..models import Invoice\n\n\ndef peek():\n    return Invoice.objects.filter(status='paid')\n"
    root = tree_with(tmp_path, {"apps/invoice/queries/ownership.py": declared, "apps/invoice/queries/peek.py": peek})
    assert unscoped_reads(root) == {("apps/invoice/queries/peek.py", "peek")}


def test_the_declaration_a_services_door_and_another_model_called_alike_are_not_reads(tmp_path):
    root = tree_with(
        tmp_path,
        {
            "apps/sale/services/peek.py": "from apps.sale.models import Sale\n\n\ndef peek():\n    return Sale.objects.all()\n",
            "apps/shop/queries.py": "from apps.shop.models import Sale\n\n\ndef peek():\n    return Sale.objects.all()\n",
        },
    )
    assert unscoped_reads(root) == set()
