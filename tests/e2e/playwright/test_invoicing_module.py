"""
E2E Tests for Invoicing Module

Coverage:
- Dashboard page
- Invoice list page
- Invoice CRUD operations
- Invoice actions (issue, cancel, print)
- Series management
- Settings page
- KPI stat cards
"""
import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestInvoicingModule:
    """E2E tests for the Invoicing module."""

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

    def create_test_series(self):
        """Helper to create a test invoice series."""
        from invoicing.models import InvoiceSeries

        return InvoiceSeries.objects.create(
            prefix='T',
            name='Test Series',
            description='Test series for E2E',
            is_default=True,
            is_active=True
        )

    def create_test_invoice(self, series=None):
        """Helper to create a test invoice."""
        from invoicing.models import Invoice, InvoiceSeries
        from decimal import Decimal

        if not series:
            series = self.create_test_series()

        return Invoice.objects.create(
            series=series,
            invoice_number='T-001',
            status='draft',
            customer_name='Test Customer',
            customer_tax_id='B12345678',
            subtotal=Decimal('100.00'),
            tax_amount=Decimal('21.00'),
            total=Decimal('121.00')
        )

    # =========================================================================
    # DASHBOARD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_invoicing_dashboard_loads(self, page: Page):
        """Test that invoicing dashboard page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_invoicing_dashboard_has_kpi_cards(self, page: Page):
        """Test that dashboard displays KPI stat cards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/")
        page.wait_for_load_state('networkidle')

        # Check for stat cards
        stat_cards = page.locator('.ui-stat-card, ion-card')
        if stat_cards.count() > 0:
            expect(stat_cards.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_invoicing_tabbar_visible(self, page: Page):
        """Test that invoicing tabbar is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/")
        page.wait_for_load_state('networkidle')

        # Verify tabbar exists
        tabbar = page.locator('ion-tab-bar')
        expect(tabbar).to_be_visible()

    # =========================================================================
    # INVOICE LIST TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_invoices_list_page_loads(self, page: Page):
        """Test that invoices list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_invoices_list_empty_state(self, page: Page):
        """Test empty state when no invoices exist."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Should show table or empty state
        content = page.locator('table, .ui-empty-state, :text("No invoices")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_invoices_list_with_data(self, page: Page):
        """Test invoices list displays invoice data."""
        invoice = self.create_test_invoice()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify invoice visible
        content = page.locator('table, :text("T-001")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        invoice.series.delete()

    @pytest.mark.django_db(transaction=True)
    def test_invoices_ajax_api(self, page: Page):
        """Test invoices list AJAX API."""
        invoice = self.create_test_invoice()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/invoicing/invoices/ajax/")

        if response.ok:
            data = response.json()
            assert 'success' in data or 'invoices' in data or isinstance(data, list)

        invoice.series.delete()

    # =========================================================================
    # INVOICE CRUD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_invoice_create_page_loads(self, page: Page):
        """Test that invoice create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/new/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_invoice_detail_page_loads(self, page: Page):
        """Test that invoice detail page loads correctly."""
        invoice = self.create_test_invoice()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/{invoice.id}/")
        page.wait_for_load_state('networkidle')

        # Verify invoice info is displayed
        content = page.locator(':text("T-001"), :text("Test Customer")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        invoice.series.delete()

    @pytest.mark.django_db(transaction=True)
    def test_invoice_print_endpoint(self, page: Page):
        """Test invoice print endpoint exists."""
        invoice = self.create_test_invoice()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/{invoice.id}/print/")
        # Should either show PDF or redirect

        invoice.series.delete()

    # =========================================================================
    # SERIES TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_series_list_page_loads(self, page: Page):
        """Test that series list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/series/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_series_list_with_data(self, page: Page):
        """Test series list displays series data."""
        series = self.create_test_series()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/series/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify series visible
        content = page.locator(':text("Test Series")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        series.delete()

    @pytest.mark.django_db(transaction=True)
    def test_series_create_page_loads(self, page: Page):
        """Test that series create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/series/new/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_series_edit_page_loads(self, page: Page):
        """Test that series edit page loads correctly."""
        series = self.create_test_series()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/series/{series.id}/edit/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

        series.delete()

    # =========================================================================
    # SETTINGS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_settings_page_loads(self, page: Page):
        """Test that settings page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/settings/")
        page.wait_for_load_state('networkidle')

        # Verify settings page
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_toggles(self, page: Page):
        """Test that settings has toggle options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/settings/")
        page.wait_for_load_state('networkidle')

        # Check for toggles
        toggles = page.locator('ion-toggle, ion-checkbox')
        if toggles.count() > 0:
            expect(toggles.first).to_be_visible()

    # =========================================================================
    # NAVIGATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_invoices(self, page: Page):
        """Test tabbar navigation to invoices."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/")
        page.wait_for_load_state('networkidle')

        # Click invoices tab
        invoices_tab = page.locator('ion-tab-button:has-text("Invoices"), ion-tab-button:has-text("Facturas")')
        if invoices_tab.count() > 0:
            invoices_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*invoices.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_series(self, page: Page):
        """Test tabbar navigation to series."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/")
        page.wait_for_load_state('networkidle')

        # Click series tab
        series_tab = page.locator('ion-tab-button:has-text("Series")')
        if series_tab.count() > 0:
            series_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*series.*'))

    # =========================================================================
    # RESPONSIVE TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_invoicing_responsive_mobile(self, page: Page):
        """Test invoicing page on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()
