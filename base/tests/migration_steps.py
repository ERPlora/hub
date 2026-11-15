"""What a migration runs on a database, read from its operations rather than by running it."""

from collections.abc import Iterable, Iterator
from importlib import import_module

from django.db import migrations


def _database_steps(operations: Iterable) -> Iterator:
    for operation in operations:
        if isinstance(operation, migrations.SeparateDatabaseAndState):
            yield from _database_steps(operation.database_operations)
        else:
            yield operation


def python_steps(module: str) -> list[str]:
    """The functions ``migrate`` calls for the migration ``module``, those hidden in a ``SeparateDatabaseAndState``
    included."""
    operations = import_module(module).Migration.operations
    return [step.code.__name__ for step in _database_steps(operations) if isinstance(step, migrations.RunPython)]
