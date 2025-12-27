"""
Pytest configuration and fixtures for CPOS Hub tests
"""
import sys
import pytest
import shutil
from pathlib import Path
from django.contrib.auth import get_user_model
from django.conf import settings


# =============================================================================
# MODULE PATH CONFIGURATION
# =============================================================================
# Add modules directory to Python path so tests can import module code
# This allows each module to have its own tests/ folder that pytest can find

def _add_modules_to_path():
    """Add the modules directory to sys.path for test discovery."""
    modules_dir = getattr(settings, 'MODULES_DIR', None)
    if modules_dir and Path(modules_dir).exists():
        modules_path = str(modules_dir)
        if modules_path not in sys.path:
            sys.path.insert(0, modules_path)
        # Also add each module directory for direct imports
        for module_dir in Path(modules_dir).iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith(('.', '_')):
                module_path = str(module_dir)
                if module_path not in sys.path:
                    sys.path.insert(0, module_path)


_add_modules_to_path()


def pytest_configure(config):
    """
    Configure pytest to discover tests in modules directory.
    Called after command line options have been parsed.
    """
    # Register custom markers for module tests
    config.addinivalue_line("markers", "module: Tests for installed modules")


def pytest_collect_file(parent, file_path):
    """
    Custom test collection hook to discover tests in modules directory.
    This allows each module to have its own tests/ folder.
    """
    modules_dir = getattr(settings, 'MODULES_DIR', None)
    if not modules_dir:
        return None

    modules_path = Path(modules_dir)
    if not modules_path.exists():
        return None

    # Check if this file is inside a module's tests directory
    try:
        # Check if file is under modules directory
        file_path.relative_to(modules_path)
        # It's a module test file - let pytest handle it normally
        if file_path.name.startswith('test_') and file_path.suffix == '.py':
            return pytest.Module.from_parent(parent, path=file_path)
    except ValueError:
        # File is not under modules directory
        pass

    return None


def pytest_ignore_collect(collection_path, config):
    """
    Don't ignore tests in modules directory.
    """
    modules_dir = getattr(settings, 'MODULES_DIR', None)
    if not modules_dir:
        return None

    modules_path = Path(modules_dir)
    try:
        # If path is under modules, don't ignore it
        collection_path.relative_to(modules_path)
        # But ignore disabled modules (starting with _ or .)
        parts = collection_path.parts
        for part in parts:
            if part.startswith('_') or part.startswith('.'):
                return True
        return False
    except ValueError:
        return None


# Disable debug toolbar during tests to avoid djdt URL namespace errors
if 'debug_toolbar' in settings.INSTALLED_APPS:
    settings.INSTALLED_APPS = [
        app for app in settings.INSTALLED_APPS if app != 'debug_toolbar'
    ]
if hasattr(settings, 'MIDDLEWARE'):
    settings.MIDDLEWARE = [
        m for m in settings.MIDDLEWARE
        if 'debug_toolbar' not in m
    ]

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
