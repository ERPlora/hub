"""Fixtures shared by control's tests."""

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext

from base.registry import REGISTRY_SCOPE


@pytest.fixture
def admin_ctx():
    """A platform admin (staff and superuser) acting on the registry, as the Hub admin's actions do."""
    root = get_user_model().objects.create_user(username="root", password="pw", is_staff=True, is_superuser=True)
    return OperationContext(scope=REGISTRY_SCOPE, actor=root, permissions=frozenset(), language="en")
