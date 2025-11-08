"""
Pytest configuration and fixtures for CPOS Hub tests
"""
import pytest
import shutil
from pathlib import Path
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture(autouse=True)
def cleanup_test_artifacts():
    """
    Automatically cleanup test artifacts after each test.
    This prevents test directories (C:/, /home/testuser/, etc.) from being created.
    """
    yield  # Run the test

    # Cleanup after test
    test_dirs = [
        'C:',
        'C:\\',
        Path('home/testuser'),
        Path('Users/testuser'),
    ]

    for test_dir in test_dirs:
        dir_path = Path(test_dir)
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
            except Exception:
                pass  # Ignore errors during cleanup


@pytest.fixture
def user(db):
    """
    Create a standard user for testing
    """
    return User.objects.create_user(
        username='testuser',
        email='testuser@example.com',
        password='testpass123'
    )


@pytest.fixture
def superuser(db):
    """
    Create a superuser for testing
    """
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='adminpass123'
    )


@pytest.fixture
def hub_config(db):
    """
    Create a HubConfig instance for testing
    Will be implemented once HubConfig model is created
    """
    # TODO: Implement when HubConfig model exists
    pass


@pytest.fixture
def api_client():
    """
    Django test client for API requests
    """
    from django.test import Client
    return Client()
