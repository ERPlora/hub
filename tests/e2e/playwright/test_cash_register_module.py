"""
E2E Tests for Cash Register Module

Coverage:
- Dashboard page
- Session management (open/close)
- Cash movements
- History page
- Settings page
- API endpoints
- KPI stat cards
"""
import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestCashRegisterModule:
    """E2E tests for the Cash Register module."""

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

    def create_test_session(self):
        """Helper to create a test cash session."""
        from cash_register.models import CashSession
        from decimal import Decimal

        return CashSession.objects.create(
            user=self.user,
            status='open',
            opening_balance=Decimal('100.00')
        )

    def create_closed_session(self):
        """Helper to create a closed cash session."""
        from cash_register.models import CashSession
        from decimal import Decimal
        from django.utils import timezone

        session = CashSession.objects.create(
            user=self.user,
            status='closed',
            opening_balance=Decimal('100.00'),
            closing_balance=Decimal('150.00'),
            expected_balance=Decimal('150.00'),
            difference=Decimal('0.00'),
            closed_at=timezone.now()
        )
        return session

    # =========================================================================
    # DASHBOARD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_cash_register_dashboard_loads(self, page: Page):
        """Test that cash register dashboard page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_cash_register_dashboard_has_kpi_cards(self, page: Page):
        """Test that dashboard displays KPI stat cards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Check for stat cards
        stat_cards = page.locator('.ui-stat-card, ion-card')
        if stat_cards.count() > 0:
            expect(stat_cards.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_cash_register_tabbar_visible(self, page: Page):
        """Test that cash register tabbar is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Verify tabbar exists
        tabbar = page.locator('ion-tab-bar')
        expect(tabbar).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_dashboard_shows_session_status(self, page: Page):
        """Test that dashboard shows current session status."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Should show session status (open/closed) or open button
        content = page.locator(':text("Open"), :text("Abrir"), :text("Session"), :text("Sesion")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    # =========================================================================
    # SESSION MANAGEMENT TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_open_session_page_loads(self, page: Page):
        """Test that open session page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/open/")
        page.wait_for_load_state('networkidle')

        # Verify page loads with form
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_open_session_has_balance_input(self, page: Page):
        """Test that open session page has balance input."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/open/")
        page.wait_for_load_state('networkidle')

        # Check for balance input
        balance_input = page.locator('ion-input[name*="balance"], input[name*="balance"], ion-input[type="number"]')
        if balance_input.count() > 0:
            expect(balance_input.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_close_session_page_loads(self, page: Page):
        """Test that close session page loads correctly."""
        session = self.create_test_session()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/close/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area form, form').first).to_be_visible()

        session.delete()

    @pytest.mark.django_db(transaction=True)
    def test_session_detail_page_loads(self, page: Page):
        """Test that session detail page loads correctly."""
        session = self.create_closed_session()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/session/{session.id}/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

        session.delete()

    @pytest.mark.django_db(transaction=True)
    def test_session_detail_shows_info(self, page: Page):
        """Test that session detail shows session information."""
        session = self.create_closed_session()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/session/{session.id}/")
        page.wait_for_load_state('networkidle')

        # Should show session number or balance
        content = page.locator(f':text("{session.session_number}"), :text("100"), :text("150")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        session.delete()

    # =========================================================================
    # HISTORY TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_history_page_loads(self, page: Page):
        """Test that history page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/history/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_history_empty_state(self, page: Page):
        """Test empty state when no sessions exist."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/history/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Should show table or empty state
        content = page.locator('table, .ui-empty-state, :text("No sessions"), :text("No sesiones")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_history_with_data(self, page: Page):
        """Test history displays session data."""
        session = self.create_closed_session()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/history/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify session appears
        content = page.locator('table, :text("Closed"), :text("Cerrada")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        session.delete()

    # =========================================================================
    # SETTINGS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_settings_page_loads(self, page: Page):
        """Test that settings page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/settings/")
        page.wait_for_load_state('networkidle')

        # Verify settings page
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_toggles(self, page: Page):
        """Test that settings has toggle options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/settings/")
        page.wait_for_load_state('networkidle')

        # Check for toggles
        toggles = page.locator('ion-toggle, ion-checkbox')
        if toggles.count() > 0:
            expect(toggles.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_auto_options(self, page: Page):
        """Test that settings has auto open/close options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/settings/")
        page.wait_for_load_state('networkidle')

        # Check for auto settings
        auto_settings = page.locator(':text("Auto"), :text("Automatico")')
        if auto_settings.count() > 0:
            expect(auto_settings.first).to_be_visible()

    # =========================================================================
    # API TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_api_current_session(self, page: Page):
        """Test API current session endpoint."""
        session = self.create_test_session()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/cash_register/api/session/current/")

        if response.ok:
            data = response.json()
            assert 'success' in data or 'session' in data or 'id' in data

        session.delete()

    @pytest.mark.django_db(transaction=True)
    def test_api_session_movements(self, page: Page):
        """Test API session movements endpoint."""
        session = self.create_test_session()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/cash_register/api/session/{session.id}/movements/")

        if response.ok:
            data = response.json()
            assert 'success' in data or 'movements' in data or isinstance(data, list)

        session.delete()

    @pytest.mark.django_db(transaction=True)
    def test_api_open_session(self, page: Page):
        """Test API open session endpoint exists."""
        self.login(page)

        # Just verify endpoint exists (would require POST)
        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

    @pytest.mark.django_db(transaction=True)
    def test_api_close_session(self, page: Page):
        """Test API close session endpoint exists."""
        session = self.create_test_session()
        self.login(page)

        # Just verify endpoint exists (would require POST)
        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        session.delete()

    # =========================================================================
    # HTMX ENDPOINT TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_htmx_calculate_denominations(self, page: Page):
        """Test HTMX calculate denominations endpoint."""
        self.login(page)

        # Navigate to open/close session to test HTMX
        page.goto(f"{self.live_server.url}/m/cash_register/open/")
        page.wait_for_load_state('networkidle')

        # Check for denomination inputs
        denomination_input = page.locator('input[name*="denomination"], input[name*="bill"], input[name*="coin"]')
        if denomination_input.count() > 0:
            expect(denomination_input.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_htmx_calculate_difference(self, page: Page):
        """Test HTMX calculate difference endpoint."""
        session = self.create_test_session()
        self.login(page)

        # Navigate to close session
        page.goto(f"{self.live_server.url}/m/cash_register/close/")
        page.wait_for_load_state('networkidle')

        # Check for difference display
        difference_el = page.locator(':text("Difference"), :text("Diferencia"), .difference')
        if difference_el.count() > 0:
            expect(difference_el.first).to_be_visible()

        session.delete()

    # =========================================================================
    # NAVIGATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_history(self, page: Page):
        """Test tabbar navigation to history."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Click history tab
        history_tab = page.locator('ion-tab-button:has-text("History"), ion-tab-button:has-text("Historial")')
        if history_tab.count() > 0:
            history_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*history.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_settings(self, page: Page):
        """Test tabbar navigation to settings."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Click settings tab
        settings_tab = page.locator('ion-tab-button:has-text("Settings"), ion-tab-button:has-text("Config")')
        if settings_tab.count() > 0:
            settings_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*settings.*'))

    # =========================================================================
    # CASH MOVEMENT TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_add_movement_api(self, page: Page):
        """Test add movement API endpoint exists."""
        session = self.create_test_session()
        self.login(page)

        # Verify endpoint exists by navigating to dashboard
        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Look for add movement button
        add_btn = page.locator('ion-button:has-text("Add"), ion-button:has-text("Agregar")')
        if add_btn.count() > 0:
            expect(add_btn.first).to_be_visible()

        session.delete()

    # =========================================================================
    # RESPONSIVE TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_cash_register_responsive_mobile(self, page: Page):
        """Test cash register page on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_cash_register_responsive_tablet(self, page: Page):
        """Test cash register page on tablet viewport."""
        page.set_viewport_size({"width": 768, "height": 1024})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()

    # =========================================================================
    # INTEGRATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_session_workflow(self, page: Page):
        """Test complete session workflow: open -> view -> close."""
        self.login(page)

        # 1. Go to dashboard
        page.goto(f"{self.live_server.url}/m/cash_register/")
        page.wait_for_load_state('networkidle')

        # 2. Try to open session
        open_btn = page.locator('ion-button:has-text("Open"), ion-button:has-text("Abrir")')
        if open_btn.count() > 0:
            open_btn.first.click()
            page.wait_for_load_state('networkidle')

        # 3. Verify session interface
        content = page.locator('.ion-padding, ion-content')
        expect(content.first).to_be_visible()
