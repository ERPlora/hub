"""Fixtures of the tenancy tests."""

import pytest

from base.tenancy import context


@pytest.fixture
def no_test_fallback(monkeypatch):
    """The test runs as production does: without a context, a hub's model or operation fails (``HubContextMissing``),
    instead of the shared database the rest of the suite falls back on (``conftest.py``)."""
    monkeypatch.setattr(context, "_test_fallback", None)
