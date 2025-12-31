"""
Playwright E2E Tests for django-components based pages.

Tests the new component-based pages across all migrated modules.
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class BaseComponentTest:
    """Base class with common setup for component tests."""

    @pytest.fixture(autouse=True)
    def setup_user(self, live_server):
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
        yield
        self.user.delete()

    def login(self, page: Page):
        """Helper to login with PIN."""
        page.goto(f"{self.live_server.url}/login/")
        page.wait_for_load_state('networkidle')

        # Wait for Ionic components to be ready
        page.wait_for_selector('ion-input', timeout=5000)

        # Fill email - Ionic input needs special handling
        email_input = page.locator('ion-input[name="email"] input, input[name="email"]').first
        email_input.fill('test@test.com')

        # Fill PIN
        pin_input = page.locator('ion-input[name="pin"] input, input[name="pin"]').first
        pin_input.fill('1234')

        # Submit
        page.locator('ion-button[type="submit"]').click()

        # Wait for redirect
        page.wait_for_url(f"{self.live_server.url}/", timeout=10000)


class TestInventoryProductsPage(BaseComponentTest):
    """E2E tests for inventory products page with django-components."""

    @pytest.mark.django_db(transaction=True)
    def test_products_page_loads_with_components(self, page: Page):
        """Test that products page loads with django-components."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Verify list_page component renders title
        expect(page.locator('h1')).to_contain_text('Products')

        # Verify filter_bar component renders search input
        expect(page.locator('input[name="search"]')).to_be_visible()

        # Verify action buttons from filter_bar actions slot
        expect(page.locator('ion-button[title*="Import"]')).to_be_visible()
        expect(page.locator('ion-button[title*="Export"]')).to_be_visible()
        expect(page.locator('ion-button[title*="New"]')).to_be_visible()

        # Verify table container from content slot
        expect(page.locator('#products-table-container')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_search_filter_triggers_htmx(self, page: Page):
        """Test that search filter from filter_bar component triggers HTMX."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Type in search
        search_input = page.locator('input[name="search"]')
        search_input.fill('test product')

        # Wait for HTMX response (debounced 400ms + request time)
        page.wait_for_timeout(1000)

        # Search should be reflected in URL via hx-push-url
        expect(page).to_have_url(re.compile(r'.*search=.*'))


class TestInventoryCategoriesPage(BaseComponentTest):
    """E2E tests for inventory categories page with django-components."""

    @pytest.mark.django_db(transaction=True)
    def test_categories_page_loads_with_components(self, page: Page):
        """Test that categories page loads with django-components."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/categories/")
        page.wait_for_load_state('networkidle')

        # Verify list_page component renders title
        expect(page.locator('h1')).to_contain_text('Categories')

        # Verify filter_bar component renders search input
        expect(page.locator('input[name="search"]')).to_be_visible()

        # Verify table container
        expect(page.locator('#categories-table-container')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_categories_has_action_buttons(self, page: Page):
        """Test that categories page has import/export/new buttons."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/categories/")
        page.wait_for_load_state('networkidle')

        # Verify action buttons
        expect(page.locator('ion-button[title*="Import"]')).to_be_visible()
        expect(page.locator('ion-button[title*="Export"]')).to_be_visible()
        expect(page.locator('ion-button[title*="New"]')).to_be_visible()


class TestInvoicesPage(BaseComponentTest):
    """E2E tests for invoicing invoices page with django-components."""

    @pytest.mark.django_db(transaction=True)
    def test_invoices_page_loads_with_components(self, page: Page):
        """Test that invoices page loads with django-components."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/")
        page.wait_for_load_state('networkidle')

        # Verify list_page component renders title
        expect(page.locator('h1')).to_contain_text('Invoices')

        # Verify filter_bar component renders search input
        expect(page.locator('input[name="search"]')).to_be_visible()

        # Verify table container
        expect(page.locator('#invoices-table-container')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_invoices_has_date_filters(self, page: Page):
        """Test that invoices page has date range filters."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/")
        page.wait_for_load_state('networkidle')

        # Verify date filter inputs from filter_bar filters slot
        expect(page.locator('input[name="date_from"]')).to_be_visible()
        expect(page.locator('input[name="date_to"]')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_invoices_has_status_filter(self, page: Page):
        """Test that invoices page has status filter."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/invoicing/invoices/")
        page.wait_for_load_state('networkidle')

        # Verify status select from filter_bar filters slot
        status_select = page.locator('select[name="status"]')
        expect(status_select).to_be_visible()

        # Verify options
        expect(status_select.locator('option[value="draft"]')).to_be_visible()
        expect(status_select.locator('option[value="issued"]')).to_be_visible()
        expect(status_select.locator('option[value="paid"]')).to_be_visible()


class TestSalesHistoryPage(BaseComponentTest):
    """E2E tests for sales history page with django-components."""

    @pytest.mark.django_db(transaction=True)
    def test_sales_history_page_loads_with_components(self, page: Page):
        """Test that sales history page loads with django-components."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sales/history/")
        page.wait_for_load_state('networkidle')

        # Verify list_page component renders title
        expect(page.locator('h1')).to_contain_text('Sales')

        # Verify filter_bar component renders search input
        expect(page.locator('input[name="search"]')).to_be_visible()

        # Verify table container
        expect(page.locator('#sales-table-container')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_sales_history_has_filters(self, page: Page):
        """Test that sales history has date and status filters."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sales/history/")
        page.wait_for_load_state('networkidle')

        # Verify date filters
        expect(page.locator('input[name="date_from"]')).to_be_visible()
        expect(page.locator('input[name="date_to"]')).to_be_visible()

        # Verify status filter
        expect(page.locator('select[name="status"]')).to_be_visible()


class TestAlpineUIStore(BaseComponentTest):
    """Tests for Alpine.js $store.ui functionality."""

    @pytest.mark.django_db(transaction=True)
    def test_alpine_store_available(self, page: Page):
        """Test that Alpine.js $store.ui is available."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Check Alpine store is initialized
        result = page.evaluate('''() => {
            return typeof Alpine !== 'undefined' &&
                   typeof Alpine.store === 'function' &&
                   typeof Alpine.store('ui') !== 'undefined';
        }''')

        assert result is True, "Alpine.js $store.ui should be available"

    @pytest.mark.django_db(transaction=True)
    def test_ui_store_has_required_methods(self, page: Page):
        """Test that $store.ui has all required methods."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Check store methods
        result = page.evaluate('''() => {
            const ui = Alpine.store('ui');
            return {
                hasToast: typeof ui.toast === 'function',
                hasSuccess: typeof ui.success === 'function',
                hasError: typeof ui.error === 'function',
                hasGetCsrfToken: typeof ui.getCsrfToken === 'function',
                hasConfirmDelete: typeof ui.confirmDelete === 'function'
            };
        }''')

        assert result['hasToast'], "$store.ui.toast should exist"
        assert result['hasSuccess'], "$store.ui.success should exist"
        assert result['hasError'], "$store.ui.error should exist"
        assert result['hasGetCsrfToken'], "$store.ui.getCsrfToken should exist"
        assert result['hasConfirmDelete'], "$store.ui.confirmDelete should exist"

    @pytest.mark.django_db(transaction=True)
    def test_csrf_token_available(self, page: Page):
        """Test CSRF token is available via list_page component."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Check CSRF token is in page
        csrf_present = page.evaluate('''() => {
            const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
            return csrfInput !== null && csrfInput.value.length > 0;
        }''')

        assert csrf_present, "CSRF token should be present from list_page component"


class TestHTMXIntegration(BaseComponentTest):
    """Tests for HTMX integration with components."""

    @pytest.mark.django_db(transaction=True)
    def test_search_has_htmx_attributes(self, page: Page):
        """Test HTMX attributes on search input from filter_bar."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        search_input = page.locator('input[name="search"]')

        # Verify HTMX attributes
        hx_get = search_input.get_attribute('hx-get')
        hx_target = search_input.get_attribute('hx-target')
        hx_trigger = search_input.get_attribute('hx-trigger')

        assert hx_get is not None, "Search should have hx-get"
        assert hx_target == '#products-table-container', "Search should target table container"
        assert 'keyup' in hx_trigger, "Search should trigger on keyup"
        assert 'delay' in hx_trigger, "Search should have debounce delay"

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_oob_swap_present(self, page: Page):
        """Test that tabbar container exists for OOB swaps."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Should have tabbar container
        tabbar = page.locator('#dashboard-tabbar, ion-tab-bar')
        expect(tabbar.first).to_be_visible()


class TestComponentConsistency(BaseComponentTest):
    """Tests to verify component consistency across pages."""

    @pytest.mark.django_db(transaction=True)
    def test_all_list_pages_have_consistent_structure(self, page: Page):
        """Test that all migrated list pages have consistent component structure."""
        self.login(page)

        pages = [
            '/m/inventory/products/',
            '/m/inventory/categories/',
            '/m/invoicing/invoices/',
            '/m/sales/history/',
        ]

        for url_path in pages:
            page.goto(f"{self.live_server.url}{url_path}")
            page.wait_for_load_state('networkidle')

            # All should have h1 title
            expect(page.locator('h1')).to_be_visible()

            # All should have search input
            expect(page.locator('input[name="search"]')).to_be_visible()

            # All should have ion-card structure
            expect(page.locator('ion-card').first).to_be_visible()
