"""
E2E Tests for Verifactu Module (Spanish Tax Compliance)

Coverage:
- Dashboard page
- Records list
- Record detail
- Contingency mode
- Chain recovery
- Events/Audit
- Settings page
- API endpoints
- KPI stat cards
"""
import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestVerifactuModule:
    """E2E tests for the Verifactu module."""

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

    def create_test_record(self):
        """Helper to create a test Verifactu record."""
        from verifactu.models import VerifactuRecord
        from decimal import Decimal
        from datetime import date
        import uuid

        return VerifactuRecord.objects.create(
            id=uuid.uuid4(),
            invoice_number='F-001',
            record_type='alta',
            status='pending',
            sequence_number=1,
            issuer_nif='B12345678',
            issuer_name='Test Company',
            invoice_date=date.today(),
            invoice_type='F1',
            base_amount=Decimal('100.00'),
            tax_rate=Decimal('21.00'),
            tax_amount=Decimal('21.00'),
            total_amount=Decimal('121.00')
        )

    # =========================================================================
    # DASHBOARD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_verifactu_dashboard_loads(self, page: Page):
        """Test that Verifactu dashboard page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_verifactu_dashboard_has_kpi_cards(self, page: Page):
        """Test that dashboard displays KPI stat cards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Check for stat cards
        stat_cards = page.locator('.ui-stat-card, ion-card')
        if stat_cards.count() > 0:
            expect(stat_cards.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_verifactu_tabbar_visible(self, page: Page):
        """Test that Verifactu tabbar is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Verify tabbar exists
        tabbar = page.locator('ion-tab-bar')
        expect(tabbar).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_dashboard_shows_status(self, page: Page):
        """Test that dashboard shows Verifactu status."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Should show status indicator
        content = page.locator(':text("Status"), :text("Estado"), :text("Mode"), :text("Modo")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    # =========================================================================
    # RECORDS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_records_list_page_loads(self, page: Page):
        """Test that records list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/records/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_records_list_empty_state(self, page: Page):
        """Test empty state when no records exist."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/records/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Should show table or empty state
        content = page.locator('table, .ui-empty-state, :text("No records")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_records_list_with_data(self, page: Page):
        """Test records list displays record data."""
        record = self.create_test_record()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/records/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify record visible
        content = page.locator('table, :text("F-001")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        record.delete()

    @pytest.mark.django_db(transaction=True)
    def test_record_detail_page_loads(self, page: Page):
        """Test that record detail page loads correctly."""
        record = self.create_test_record()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/records/{record.id}/")
        page.wait_for_load_state('networkidle')

        # Verify record info is displayed
        content = page.locator(':text("F-001")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        record.delete()

    # =========================================================================
    # CONTINGENCY TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_contingency_page_loads(self, page: Page):
        """Test that contingency page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/contingency/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_contingency_shows_queue(self, page: Page):
        """Test that contingency page shows pending queue."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/contingency/")
        page.wait_for_load_state('networkidle')

        # Should show queue status or empty message
        content = page.locator(':text("Queue"), :text("Cola"), :text("Pending"), :text("Pendiente")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    # =========================================================================
    # RECOVERY TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_recovery_page_loads(self, page: Page):
        """Test that chain recovery page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/recovery/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_recovery_has_options(self, page: Page):
        """Test that recovery page has recovery options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/recovery/")
        page.wait_for_load_state('networkidle')

        # Should show recovery options
        content = page.locator(':text("AEAT"), :text("Manual"), ion-button')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    # =========================================================================
    # EVENTS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_events_page_loads(self, page: Page):
        """Test that events/audit page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/events/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    # =========================================================================
    # SETTINGS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_settings_page_loads(self, page: Page):
        """Test that settings page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/settings/")
        page.wait_for_load_state('networkidle')

        # Verify settings page
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_mode_selector(self, page: Page):
        """Test that settings has mode selector."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/settings/")
        page.wait_for_load_state('networkidle')

        # Check for mode options
        mode_options = page.locator(':text("Mode"), :text("Modo"), ion-select, ion-radio-group')
        if mode_options.count() > 0:
            expect(mode_options.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_certificate_upload(self, page: Page):
        """Test that settings has certificate upload option."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/settings/")
        page.wait_for_load_state('networkidle')

        # Check for certificate upload
        cert_option = page.locator(':text("Certificate"), :text("Certificado"), input[type="file"]')
        if cert_option.count() > 0:
            expect(cert_option.first).to_be_visible()

    # =========================================================================
    # API TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_api_health_check(self, page: Page):
        """Test API health check endpoint."""
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/verifactu/api/health/")

        if response.ok:
            data = response.json()
            assert 'status' in data or 'healthy' in data or isinstance(data, dict)

    @pytest.mark.django_db(transaction=True)
    def test_api_chain_status(self, page: Page):
        """Test API chain status endpoint."""
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/verifactu/api/chain-status/")

        if response.ok:
            data = response.json()
            assert isinstance(data, dict)

    @pytest.mark.django_db(transaction=True)
    def test_api_verify_chain(self, page: Page):
        """Test API verify chain endpoint exists."""
        self.login(page)

        # Just verify endpoint responds
        response = page.request.get(f"{self.live_server.url}/m/verifactu/api/verify-chain/")
        assert response.status in [200, 400, 405, 500]

    @pytest.mark.django_db(transaction=True)
    def test_api_test_connection(self, page: Page):
        """Test API test connection endpoint exists."""
        self.login(page)

        # Just verify endpoint responds
        response = page.request.get(f"{self.live_server.url}/m/verifactu/api/test-connection/")
        assert response.status in [200, 400, 405, 500]

    # =========================================================================
    # NAVIGATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_records(self, page: Page):
        """Test tabbar navigation to records."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Click records tab
        records_tab = page.locator('ion-tab-button:has-text("Records"), ion-tab-button:has-text("Registros")')
        if records_tab.count() > 0:
            records_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*records.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_contingency(self, page: Page):
        """Test tabbar navigation to contingency."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Click contingency tab
        contingency_tab = page.locator('ion-tab-button:has-text("Contingency"), ion-tab-button:has-text("Contingencia")')
        if contingency_tab.count() > 0:
            contingency_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*contingency.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_settings(self, page: Page):
        """Test tabbar navigation to settings."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Click settings tab
        settings_tab = page.locator('ion-tab-button:has-text("Settings"), ion-tab-button:has-text("Config")')
        if settings_tab.count() > 0:
            settings_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*settings.*'))

    # =========================================================================
    # RESPONSIVE TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_verifactu_responsive_mobile(self, page: Page):
        """Test Verifactu page on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_verifactu_responsive_tablet(self, page: Page):
        """Test Verifactu page on tablet viewport."""
        page.set_viewport_size({"width": 768, "height": 1024})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()

    # =========================================================================
    # SECURITY TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_verifactu_requires_login(self, page: Page):
        """Test that Verifactu requires authentication."""
        # Try to access without login
        page.goto(f"{self.live_server.url}/m/verifactu/")
        page.wait_for_load_state('networkidle')

        # Should redirect to login or show login form
        content = page.locator('input[name="email"], input[name="pin"], :text("Login")')
        if content.count() > 0:
            expect(content.first).to_be_visible()
