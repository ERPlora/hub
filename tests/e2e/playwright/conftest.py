"""
Playwright E2E Tests Configuration

Provides fixtures for browser-based end-to-end testing.

IMPORTANT: Playwright tests run in an async context, but Django ORM
is synchronous. We MUST set DJANGO_ALLOW_ASYNC_UNSAFE BEFORE importing Django.
"""
import os

# CRITICAL: Set this BEFORE any Django imports
# This allows Django ORM operations from Playwright's async context
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = 'true'

import pytest
from playwright.sync_api import Page, Browser, BrowserContext

from django.test import LiveServerTestCase
from django.contrib.staticfiles.testing import StaticLiveServerTestCase


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for tests."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "en-US",
    }


@pytest.fixture
def authenticated_page(page: Page, live_server):
    """
    Create an authenticated page with a logged-in user.

    Note: This fixture requires the live_server to be running
    and creates a test user for authentication.
    """
    from apps.accounts.models import LocalUser

    # Create test user
    user = LocalUser.objects.create(
        name='E2E Test User',
        email='e2e@test.com',
        role='admin',
        is_active=True
    )
    user.set_pin('1234')

    # Navigate to login
    page.goto(f"{live_server.url}/login/")

    # Login via PIN
    page.fill('input[name="email"]', 'e2e@test.com')
    page.fill('input[name="pin"]', '1234')
    page.click('button[type="submit"]')

    # Wait for redirect to home
    page.wait_for_url(f"{self.live_server.url}/", timeout=5000)

    yield page

    # Cleanup
    user.delete()


@pytest.fixture
def live_server_url(live_server):
    """Return the live server URL."""
    return live_server.url


@pytest.fixture
def customers_module(db):
    """
    Marker fixture to indicate tests require the customers module.
    The module is loaded from modules/ directory by the runtime manager.
    No database entry needed - modules are loaded from filesystem.
    """
    return True


@pytest.fixture
def installed_modules(db):
    """
    Marker fixture to indicate tests require all modules.
    Modules are loaded from modules/ directory by the runtime manager.
    No database entry needed - modules are loaded from filesystem.
    """
    return True
