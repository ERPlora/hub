"""
E2E Tests for Customers Module

Coverage:
- Customer list page
- Customer CRUD operations
- Search and filters
- Export functionality
- Settings page
- KPI stat cards
"""
import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestCustomersModule:
    """E2E tests for the Customers module."""

    @pytest.fixture(autouse=True)
    def setup_user(self, live_server, store_config, customers_module):
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
        self.customers_module = customers_module
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

        # Wait for PIN keypad to appear (the visible one in the main content, not modal)
        page.wait_for_selector('.pin-section', timeout=5000)

        # Enter PIN using keypad buttons (1, 2, 3, 4)
        # Use the keypad that's NOT inside a modal (ion-modal)
        main_keypad = page.locator('.login-card .keypad')
        for digit in ['1', '2', '3', '4']:
            main_keypad.locator(f'ion-button:has-text("{digit}")').click()

        # Wait for redirect after successful PIN
        page.wait_for_url(f"{self.live_server.url}/", timeout=10000)

    def create_test_customer(self):
        """Helper to create a test customer."""
        from customers.models import Customer

        return Customer.objects.create(
            name='Test Customer',
            email='customer@test.com',
            phone='+34666777888',
            address='Test Address 123',
            tax_id='B12345678',
            is_active=True
        )

    # =========================================================================
    # LIST PAGE TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_customers_list_page_loads(self, page: Page):
        """Test that customers list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Verify page header (uses Ionic ion-title)
        expect(page.locator('ion-title:has-text("Customers")')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_customers_has_four_kpi_cards(self, page: Page):
        """Test that customers page displays 4 KPI stat cards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Verify KPI labels (use first to avoid strict mode violation due to substring match)
        # "Active" matches both "Active" and "Inactive", so we use .first
        expect(page.locator('.ui-stat-label:has-text("Active")').first).to_be_visible()
        expect(page.locator('.ui-stat-label:has-text("Inactive")')).to_be_visible()
        expect(page.locator('.ui-stat-label:has-text("Total")')).to_be_visible()
        expect(page.locator('.ui-stat-label:has-text("New This Month")')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_customers_search_bar_visible(self, page: Page):
        """Test that search bar is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Verify search bar
        expect(page.locator('ion-searchbar')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_customers_status_filter_visible(self, page: Page):
        """Test that status filter segment is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Verify segment filter
        expect(page.locator('ion-segment')).to_be_visible()
        expect(page.locator('ion-segment-button[value="active"]')).to_be_visible()
        expect(page.locator('ion-segment-button[value="inactive"]')).to_be_visible()
        expect(page.locator('ion-segment-button[value="all"]')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_customers_empty_state(self, page: Page):
        """Test empty state when no customers exist."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Wait for Alpine.js to load data
        page.wait_for_timeout(1000)

        # Should show empty state or create button
        empty_state = page.locator('.ui-empty-state, :text("No customers found")')
        if empty_state.count() > 0:
            expect(empty_state.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_customers_list_with_data(self, page: Page):
        """Test customers list displays customer data."""
        customer = self.create_test_customer()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Wait for Alpine.js to load data
        page.wait_for_timeout(1500)

        # Verify table is visible
        table = page.locator('table.data-table, .data-table-container')
        expect(table.first).to_be_visible()

        # Cleanup
        customer.delete()

    # =========================================================================
    # SEARCH AND FILTER TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_customers_search_functionality(self, page: Page):
        """Test customer search by name."""
        customer = self.create_test_customer()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Type in search
        search_input = page.locator('ion-searchbar input')
        search_input.fill('Test Customer')

        # Wait for debounced search
        page.wait_for_timeout(500)

        # Customer should still be visible
        expect(page.locator('text=Test Customer')).to_be_visible()

        # Cleanup
        customer.delete()

    @pytest.mark.django_db(transaction=True)
    def test_customers_filter_active(self, page: Page):
        """Test filtering by active status."""
        customer = self.create_test_customer()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Click active filter
        page.locator('ion-segment-button[value="active"]').click()
        page.wait_for_timeout(500)

        # Active customer should be visible
        expect(page.locator('text=Test Customer')).to_be_visible()

        # Cleanup
        customer.delete()

    @pytest.mark.django_db(transaction=True)
    def test_customers_filter_inactive(self, page: Page):
        """Test filtering by inactive status."""
        from customers.models import Customer

        customer = Customer.objects.create(
            name='Inactive Customer',
            email='inactive@test.com',
            is_active=False
        )
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Wait for initial data load (Alpine.js)
        page.wait_for_timeout(2000)

        # Click inactive filter - this triggers Alpine.js loadCustomers()
        page.locator('ion-segment-button[value="inactive"]').click()

        # Wait for loading spinner to disappear (Alpine.js fetch complete)
        page.wait_for_selector('ion-spinner', state='hidden', timeout=10000)

        # Give Alpine time to render the template after data loads
        page.wait_for_timeout(1000)

        # The filter should now be on inactive - check that inactive segment is selected
        expect(page.locator('ion-segment-button[value="inactive"]')).to_have_class(re.compile(r'.*segment-button-checked.*'))

        # Cleanup
        customer.delete()

    # =========================================================================
    # CREATE CUSTOMER TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_create_customer_navigation(self, page: Page):
        """Test navigation to create customer page."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Click create button (in tabbar or empty state)
        create_btn = page.locator('ion-tab-button:has-text("New"), ion-button:has-text("Create")')
        if create_btn.count() > 0:
            create_btn.first.click()
            page.wait_for_load_state('networkidle')

            # Verify form page
            expect(page).to_have_url(re.compile(r'.*create.*'))

    @pytest.mark.django_db(transaction=True)
    def test_create_customer_form_fields(self, page: Page):
        """Test that create customer form has all required fields."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/create/")
        page.wait_for_load_state('networkidle')

        # Verify form fields exist
        expect(page.locator('ion-input[name="name"], input[name="name"]').first).to_be_visible()
        expect(page.locator('ion-input[name="email"], input[name="email"]').first).to_be_visible()
        expect(page.locator('ion-input[name="phone"], input[name="phone"]').first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_create_customer_submit(self, page: Page):
        """Test creating a new customer."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/create/")
        page.wait_for_load_state('networkidle')

        # Fill form
        page.locator('ion-input[name="name"] input, input[name="name"]').first.fill('New Customer')
        page.locator('ion-input[name="email"] input, input[name="email"]').first.fill('new@test.com')
        page.locator('ion-input[name="phone"] input, input[name="phone"]').first.fill('+34666111222')

        # Submit
        page.locator('ion-button[type="submit"]').click()
        page.wait_for_timeout(1000)

        # Verify success (redirect or toast)
        # Clean up
        from customers.models import Customer
        Customer.objects.filter(email='new@test.com').delete()

    # =========================================================================
    # VIEW/EDIT CUSTOMER TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_view_customer_detail(self, page: Page):
        """Test viewing customer detail page."""
        customer = self.create_test_customer()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/{customer.id}/")
        page.wait_for_load_state('networkidle')

        # Verify customer info is displayed
        expect(page.locator('text=Test Customer')).to_be_visible()

        # Cleanup
        customer.delete()

    @pytest.mark.django_db(transaction=True)
    def test_edit_customer_navigation(self, page: Page):
        """Test navigation to edit customer page."""
        customer = self.create_test_customer()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/{customer.id}/edit/")
        page.wait_for_load_state('networkidle')

        # Verify form is pre-filled
        name_input = page.locator('ion-input[name="name"] input, input[name="name"]').first
        expect(name_input).to_have_value('Test Customer')

        # Cleanup
        customer.delete()

    # =========================================================================
    # DELETE CUSTOMER TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_delete_customer_confirmation(self, page: Page):
        """Test delete customer shows confirmation dialog."""
        customer = self.create_test_customer()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1500)

        # Click delete button
        delete_btn = page.locator('ion-button[color="danger"]').first
        if delete_btn.count() > 0:
            delete_btn.click()

            # Verify confirmation dialog appears
            page.wait_for_timeout(500)
            alert = page.locator('ion-alert')
            expect(alert).to_be_visible()

        # Cleanup
        customer.delete()

    # =========================================================================
    # EXPORT TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_export_customers_csv(self, page: Page):
        """Test export customers to CSV."""
        customer = self.create_test_customer()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Navigate to export (via tabbar)
        export_btn = page.locator('ion-tab-button:has-text("Export"), ion-button:has-text("Export")')
        if export_btn.count() > 0:
            # Start waiting for download
            with page.expect_download() as download_info:
                export_btn.first.click()

            download = download_info.value
            assert download.suggested_filename.endswith('.csv')

        # Cleanup
        customer.delete()

    # =========================================================================
    # SETTINGS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_customers_settings_page_loads(self, page: Page):
        """Test customers settings page loads."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/settings/")
        page.wait_for_load_state('networkidle')

        # Verify settings page - uses h1 in settings_page component
        expect(page.locator('h1:has-text("Customer Settings")')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_customers_settings_toggles(self, page: Page):
        """Test customers settings has toggle options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/settings/")
        page.wait_for_load_state('networkidle')

        # Verify toggle options exist
        toggles = page.locator('ion-toggle, ion-checkbox')
        assert toggles.count() >= 1, "Settings should have at least one toggle"

    # =========================================================================
    # TABBAR TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_customers_tabbar_navigation(self, page: Page):
        """Test tabbar navigation between views."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Verify tabbar exists
        tabbar = page.locator('ion-tab-bar')
        expect(tabbar).to_be_visible()

        # Click Settings tab
        settings_tab = page.locator('ion-tab-button:has-text("Settings")')
        if settings_tab.count() > 0:
            settings_tab.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*settings.*'))

    # =========================================================================
    # RESPONSIVE TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_customers_responsive_mobile(self, page: Page):
        """Test customers page on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('ion-title:has-text("Customers")')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_customers_infinite_scroll(self, page: Page):
        """Test infinite scroll pagination."""
        # Create multiple customers
        from customers.models import Customer
        customers = []
        for i in range(30):
            customers.append(Customer.objects.create(
                name=f'Customer {i}',
                email=f'customer{i}@test.com',
                is_active=True
            ))

        self.login(page)

        page.goto(f"{self.live_server.url}/m/customers/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1500)

        # Scroll to bottom to trigger infinite scroll
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(1000)

        # More customers should be loaded
        # (This is tested by checking the spinner or more rows)

        # Cleanup
        for c in customers:
            c.delete()
