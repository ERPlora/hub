"""The two tests ``test_reuse_db.py`` runs in a pytest of their own, on a database of their own.

Not named ``test_*.py``: the suite does not collect them, and a run that names this file does.
"""

import pytest

from apps.tax.models import TaxCategory


@pytest.mark.django_db(transaction=True)
def test_a_transactional_test():
    """Nothing to do: Django empties every table when a test like this ends, the factory data too."""


@pytest.mark.django_db
def test_finds_the_factory_data():
    assert TaxCategory.objects.exists()
