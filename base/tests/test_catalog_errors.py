"""base/catalog/errors.py: what building or writing the registry raises, every error a ``CatalogError``."""

import pytest

from base.catalog.errors import CatalogError, RegistryError, SharedSchemaNotReady, WorkbookError

PROBLEMS = ["things: icon: not baked.", "stock: WORKBOOK.md: missing."]


@pytest.mark.parametrize("error", [RegistryError(PROBLEMS), SharedSchemaNotReady(["shared.app"]), WorkbookError("x")])
def test_every_error_of_the_catalog_is_a_catalog_error(error):
    # The worker and register_apps catch CatalogError: a subclass that left it would escape them.
    assert isinstance(error, CatalogError)


def test_a_registry_error_keeps_every_problem_and_tells_one_per_line():
    error = RegistryError(PROBLEMS)

    assert error.problems == PROBLEMS
    head, *lines = str(error).split("\n")
    assert head.startswith(f"{len(PROBLEMS)} ")
    assert lines == [f"- {problem}" for problem in PROBLEMS]


def test_a_shared_schema_not_ready_names_every_missing_table():
    error = SharedSchemaNotReady(["shared.app", "shared.app_doc"])

    assert error.tables == ["shared.app", "shared.app_doc"]
    assert "shared.app, shared.app_doc" in str(error)
