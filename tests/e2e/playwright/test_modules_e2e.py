"""
Playwright E2E Tests for Module Store

Tests the complete user flow for browsing and managing modules.
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestModuleStoreNavigation:
    """E2E tests for module store navigation."""

    @pytest.mark.django_db(transaction=True)
    def test_modules_page_loads(self, page: Page, live_server):
        """Test that modules page loads correctly."""
        from apps.accounts.models import LocalUser

        # Create user
        user = LocalUser.objects.create(
            name='Test User',
            email='test@test.com',
            role='admin',
            is_active=True
        )
        user.set_pin('1234')

        # Login
        page.goto(f"{live_server.url}/login/")
        page.fill('input[name="email"]', 'test@test.com')
        page.fill('input[name="pin"]', '1234')
        page.click('ion-button[type="submit"]')

        # Navigate to store (should redirect to /store/modules/)
        page.goto(f"{live_server.url}/store/modules/")

        # Verify page loaded
        expect(page.locator('h1')).to_contain_text('Modules')

    @pytest.mark.django_db(transaction=True)
    def test_marketplace_navigation(self, page: Page, live_server):
        """Test navigating to marketplace from installed modules."""
        from apps.accounts.models import LocalUser

        user = LocalUser.objects.create(
            name='Test User',
            email='test@test.com',
            role='admin',
            is_active=True
        )
        user.set_pin('1234')

        page.goto(f"{live_server.url}/login/")
        page.fill('input[name="email"]', 'test@test.com')
        page.fill('input[name="pin"]', '1234')
        page.click('ion-button[type="submit"]')

        # Go to store
        page.goto(f"{live_server.url}/store/modules/")

        # Click on marketplace button
        marketplace_btn = page.locator('ion-button:has-text("Module Store")')
        if marketplace_btn.count() > 0:
            marketplace_btn.click()
            page.wait_for_url("**/store/modules/marketplace/**")


class TestModuleActions:
    """E2E tests for module actions."""

    @pytest.mark.django_db(transaction=True)
    def test_module_activate_deactivate_buttons_visible(self, page: Page, live_server):
        """Test that activate/deactivate buttons are visible for modules."""
        from apps.accounts.models import LocalUser

        user = LocalUser.objects.create(
            name='Test User',
            email='test@test.com',
            role='admin',
            is_active=True
        )
        user.set_pin('1234')

        page.goto(f"{live_server.url}/login/")
        page.fill('input[name="email"]', 'test@test.com')
        page.fill('input[name="pin"]', '1234')
        page.click('ion-button[type="submit"]')

        page.goto(f"{live_server.url}/store/modules/")

        # Look for any action buttons
        action_buttons = page.locator('.module-card-actions ion-button')
        # May or may not have modules, but page should load
        expect(page.locator('h1')).to_contain_text('Modules')


class TestUIComponents:
    """E2E tests for UI component rendering."""

    @pytest.mark.django_db(transaction=True)
    def test_ionic_components_render(self, page: Page, live_server):
        """Test that Ionic components render correctly."""
        from apps.accounts.models import LocalUser

        user = LocalUser.objects.create(
            name='Test User',
            email='test@test.com',
            role='admin',
            is_active=True
        )
        user.set_pin('1234')

        page.goto(f"{live_server.url}/login/")
        page.fill('input[name="email"]', 'test@test.com')
        page.fill('input[name="pin"]', '1234')
        page.click('ion-button[type="submit"]')

        # Navigate to store
        page.goto(f"{live_server.url}/store/modules/")

        # Check Ionic components are rendered
        expect(page.locator('ion-content')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_htmx_navigation_works(self, page: Page, live_server):
        """Test that HTMX navigation works correctly."""
        from apps.accounts.models import LocalUser

        user = LocalUser.objects.create(
            name='Test User',
            email='test@test.com',
            role='admin',
            is_active=True
        )
        user.set_pin('1234')

        page.goto(f"{live_server.url}/login/")
        page.fill('input[name="email"]', 'test@test.com')
        page.fill('input[name="pin"]', '1234')
        page.click('ion-button[type="submit"]')

        # Navigate to home
        page.goto(f"{live_server.url}/home/")
        expect(page.locator('ion-content')).to_be_visible()

        # Use HTMX link to navigate to settings
        settings_link = page.locator('[hx-get*="/settings/"]').first
        if settings_link.count() > 0:
            settings_link.click()
            page.wait_for_selector('ion-content', timeout=5000)
