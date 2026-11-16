"""The two tests ``test_reuse_db.py`` runs in a pytest of their own, on a database of their own.

Not named ``test_*.py``: the suite does not collect them, and a run that names this file does.
"""

import pytest
from django.db import connection

from config import testing


@pytest.mark.django_db(transaction=True)
def test_a_transactional_test():
    """Nothing to do: Django empties every table when a test like this ends, the factory data too."""


@pytest.mark.django_db
def test_finds_the_factory_data():
    """The test database ``--reuse-db`` kept: its table that speaks for the factory data has rows."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT EXISTS (SELECT FROM {connection.ops.quote_name(testing.FACTORY_TABLE)})")
        assert cursor.fetchone()[0]
