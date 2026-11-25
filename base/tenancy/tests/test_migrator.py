"""The migrator's tests: the helpers they share, and what holds for the whole package.

A test that migrates makes a database of its own, empty and named as one of this session's control database's
(``base.tenancy.names``), and drops it after; the session's hubs A and B (``hubs.py``) are only read. The migrator
registers its ``<db_name>__ddl`` alias as it goes, which a Django test case refuses (an alias in the settings and not
in its ``databases``), so these tests run without one, on the committed test database (``hubs.committed_database``,
as ``db``): the rows they write in control are deleted after each (``make_hub``).
"""

import re
from pathlib import Path

from django.db import connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader

from base.tenancy import connections as tenancy_connections
from base.tenancy.tests import hubs

PLATFORM = ("base", "live")


def leaves() -> dict[str, str]:
    """``{label: its leaf migration}`` in the code."""
    return dict(MigrationLoader(None, ignore_no_migrations=True).graph.leaf_nodes())


def control() -> str:
    return tenancy_connections.control_name()


def tables_of(apps) -> set[str]:
    return hubs.hub_tables(apps) | {"django_migrations"}


def migrate_to(db_name: str, node: tuple[str, str]) -> None:
    """Bring the database ``db_name`` to the migration ``node``, as an older code would have left it."""
    alias = tenancy_connections.register_ddl_alias(db_name)
    try:
        MigrationExecutor(connections[alias]).migrate([node])
    finally:
        connections[alias].close()


def test_the_migrator_never_drops_anything():
    """Tables are never deleted, and a template is brought up to date, never rebuilt."""
    root = Path(__file__).resolve().parents[3]
    for path in (
        "base/tenancy/migrator/__init__.py",
        "base/tenancy/migrator/app_sets.py",
        "base/tenancy/migrator/control_database.py",
        "base/tenancy/migrator/hub_templates.py",
        "base/tenancy/migrator/hubs_pass.py",
        "base/tenancy/migrator/schema.py",
        "base/tenancy/migrator/servers.py",
        "base/management/commands/migrate_hubs.py",
    ):
        assert re.search(r"\bDROP\b", (root / path).read_text()) is None, path
