"""What goes wrong building or writing the registry: ``CatalogError`` and the errors that refine it."""


class CatalogError(Exception):
    """The registry cannot be built or written; the message says what and how to fix it."""


class SharedSchemaNotReady(CatalogError):
    """The SaaS has not created the ``shared`` tables yet (its first ``migrate``): wait, not a contract gap.

    The worker waits for them (``base.worker``); a table that exists without a column the mirror
    writes is a ``CatalogError`` instead, fatal.
    """

    def __init__(self, tables: list[str]):
        self.tables = tables
        super().__init__(
            f"the SaaS has not migrated the shared schema yet: no table {', '.join(tables)} "
            "(saas-next's migrate creates them)"
        )


class WorkbookError(CatalogError):
    """A WORKBOOK whose customer's part cannot be published."""


class RegistryError(CatalogError):
    """Every problem of every module, gathered: one line each, ``<app>: <field>: <what>``."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(problems)

    def __str__(self) -> str:
        lines = "".join(f"\n- {problem}" for problem in self.problems)
        return f"{len(self.problems)} problem(s) in the apps' registry:{lines}"
