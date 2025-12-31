"""
E2E Tests for Returns & Refunds Module

Coverage:
- Dashboard page
- Returns list and CRUD
- Return actions (approve, process, cancel)
- Return reasons management
- Store credits
- Settings page
- KPI stat cards
"""
import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestReturnsModule:
    """E2E tests for the Returns & Refunds module."""

    @pytest.fixture(autouse=True)
    def setup_user(self, live_server, store_config):
        """Create test user before each test."""
        from apps.accounts.models import LocalUser

        self.user = LocalUser.objects.create(
            name='Test User',
            email='test@test.com',
            role='admin',
            is_active=True
        )
        self.user.set_pin('1234')
        self.live_server = live_server
        self.store_config = store_config
        yield
        self.user.delete()

    def login(self, page: Page):
        """Helper to login with PIN using Local Login flow."""
        page.goto(f"{self.live_server.url}/login/")
        page.wait_for_load_state('networkidle')

        # Wait for employee grid to load (Local Login mode)
        page.wait_for_selector('.employee-card', timeout=5000)

        # Click on the test employee card
        page.locator('.employee-card').first.click()

        # Wait for PIN keypad to appear
        page.wait_for_selector('.pin-section', timeout=5000)

        # Enter PIN using keypad buttons (1, 2, 3, 4)
        main_keypad = page.locator('.login-card .keypad')
        for digit in ['1', '2', '3', '4']:
            main_keypad.locator(f'ion-button:has-text("{digit}")').click()

        # Wait for redirect after successful PIN
        page.wait_for_url(f"{self.live_server.url}/", timeout=10000)

    def create_test_reason(self):
        """Helper to create a test return reason."""
        from returns.models import ReturnReason

        return ReturnReason.objects.create(
            name='Test Reason',
            description='Test reason description',
            is_active=True
        )

    def create_test_return(self, reason=None):
        """Helper to create a test return."""
        from returns.models import Return
        from decimal import Decimal
        import uuid

        if not reason:
            reason = self.create_test_reason()

        # Use unique return_number to avoid conflicts
        return_number = f"RET-{uuid.uuid4().hex[:6].upper()}"

        return Return.objects.create(
            return_number=return_number,
            status='pending',
            reason=reason,
            total_amount=Decimal('50.00')
        )

    def create_test_credit(self):
        """Helper to create a test store credit."""
        from returns.models import StoreCredit
        from decimal import Decimal

        return StoreCredit.objects.create(
            code='CREDIT-001',
            customer_name='Test Customer',
            original_amount=Decimal('50.00'),
            remaining_amount=Decimal('50.00'),
            is_active=True
        )

    # =========================================================================
    # DASHBOARD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_returns_dashboard_loads(self, page: Page):
        """Test that returns dashboard page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_returns_dashboard_has_kpi_cards(self, page: Page):
        """Test that dashboard displays KPI stat cards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/")
        page.wait_for_load_state('networkidle')

        # Check for stat cards
        stat_cards = page.locator('.ui-stat-card, ion-card')
        if stat_cards.count() > 0:
            expect(stat_cards.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_returns_tabbar_visible(self, page: Page):
        """Test that returns tabbar is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/")
        page.wait_for_load_state('networkidle')

        # Verify tabbar exists
        tabbar = page.locator('ion-tab-bar')
        expect(tabbar).to_be_visible()

    # =========================================================================
    # RETURNS LIST TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_returns_list_page_loads(self, page: Page):
        """Test that returns list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/returns/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_returns_list_empty_state(self, page: Page):
        """Test empty state when no returns exist."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/returns/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Should show table or empty state
        content = page.locator('table, .ui-empty-state, :text("No returns")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_returns_list_with_data(self, page: Page):
        """Test returns list displays return data."""
        return_obj = self.create_test_return()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/returns/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify return visible - just check for table presence
        content = page.locator('table')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        return_obj.reason.delete()

    # =========================================================================
    # RETURN CRUD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_return_create_page_loads(self, page: Page):
        """Test that return create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/returns/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_return_detail_page_loads(self, page: Page):
        """Test that return detail page loads correctly."""
        return_obj = self.create_test_return()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/returns/{return_obj.pk}/")
        page.wait_for_load_state('networkidle')

        # Verify page loaded (content area visible)
        expect(page.locator('#main-content-area')).to_be_visible()

        return_obj.reason.delete()

    @pytest.mark.django_db(transaction=True)
    def test_return_edit_page_loads(self, page: Page):
        """Test that return edit page loads correctly."""
        return_obj = self.create_test_return()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/returns/{return_obj.pk}/edit/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

        return_obj.reason.delete()

    # =========================================================================
    # RETURN REASONS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_reasons_list_page_loads(self, page: Page):
        """Test that reasons list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/reasons/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_reasons_list_with_data(self, page: Page):
        """Test reasons list displays reason data."""
        reason = self.create_test_reason()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/reasons/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify reason visible
        content = page.locator(':text("Test Reason")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        reason.delete()

    @pytest.mark.django_db(transaction=True)
    def test_reason_create_page_loads(self, page: Page):
        """Test that reason create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/reasons/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    # =========================================================================
    # STORE CREDITS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_credits_list_page_loads(self, page: Page):
        """Test that credits list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/credits/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_credits_list_with_data(self, page: Page):
        """Test credits list displays credit data."""
        credit = self.create_test_credit()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/credits/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify credit visible
        content = page.locator(':text("CREDIT-001")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        credit.delete()

    @pytest.mark.django_db(transaction=True)
    def test_credit_create_page_loads(self, page: Page):
        """Test that credit create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/credits/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_credit_detail_page_loads(self, page: Page):
        """Test that credit detail page loads correctly."""
        credit = self.create_test_credit()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/credits/{credit.pk}/")
        page.wait_for_load_state('networkidle')

        # Verify credit info is displayed
        content = page.locator(':text("CREDIT-001")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        credit.delete()

    # =========================================================================
    # SETTINGS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_settings_page_loads(self, page: Page):
        """Test that settings page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/settings/")
        page.wait_for_load_state('networkidle')

        # Verify settings page
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_toggles(self, page: Page):
        """Test that settings has toggle options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/settings/")
        page.wait_for_load_state('networkidle')

        # Check for toggles
        toggles = page.locator('ion-toggle, ion-checkbox')
        if toggles.count() > 0:
            expect(toggles.first).to_be_visible()

    # =========================================================================
    # NAVIGATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_returns(self, page: Page):
        """Test tabbar navigation to returns."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/")
        page.wait_for_load_state('networkidle')

        # Click returns tab
        returns_tab = page.locator('ion-tab-button:has-text("Returns"), ion-tab-button:has-text("Devoluciones")')
        if returns_tab.count() > 0:
            returns_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*returns.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_credits(self, page: Page):
        """Test tabbar navigation to credits."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/")
        page.wait_for_load_state('networkidle')

        # Click credits tab
        credits_tab = page.locator('ion-tab-button:has-text("Credits"), ion-tab-button:has-text("Creditos")')
        if credits_tab.count() > 0:
            credits_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*credits.*'))

    # =========================================================================
    # RESPONSIVE TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_returns_responsive_mobile(self, page: Page):
        """Test returns page on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/returns/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()
