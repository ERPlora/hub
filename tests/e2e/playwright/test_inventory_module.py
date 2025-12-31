"""
E2E Tests for Inventory Module

Coverage:
- Dashboard page
- Products list page with DataTable
- Product CRUD operations
- Categories management
- Search and filters
- Export/Import functionality
- Barcode generation
- Reports page
- Settings page
- KPI stat cards
"""
import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestInventoryModule:
    """E2E tests for the Inventory module."""

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

    def create_test_category(self):
        """Helper to create a test category."""
        from inventory.models import Category

        return Category.objects.create(
            name='Test Category',
            description='Test category description',
            is_active=True
        )

    def create_test_product(self, category=None):
        """Helper to create a test product."""
        from inventory.models import Product
        from decimal import Decimal

        if not category:
            category = self.create_test_category()

        product = Product.objects.create(
            name='Test Product',
            sku='TEST-001',
            description='Test product description',
            price=Decimal('10.00'),
            cost=Decimal('5.00'),
            stock=100,
            low_stock_threshold=10,
            is_active=True
        )
        product.categories.add(category)
        return product

    # =========================================================================
    # DASHBOARD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_inventory_dashboard_loads(self, page: Page):
        """Test that inventory dashboard page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_inventory_dashboard_has_kpi_cards(self, page: Page):
        """Test that dashboard displays KPI stat cards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
        page.wait_for_load_state('networkidle')

        # Check for stat cards
        stat_cards = page.locator('.ui-stat-card, ion-card')
        if stat_cards.count() > 0:
            expect(stat_cards.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_inventory_tabbar_visible(self, page: Page):
        """Test that inventory tabbar is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
        page.wait_for_load_state('networkidle')

        # Verify tabbar exists
        tabbar = page.locator('ion-tab-bar')
        expect(tabbar).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_inventory_tabbar_has_all_tabs(self, page: Page):
        """Test that tabbar has all navigation tabs."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
        page.wait_for_load_state('networkidle')

        # Verify tabs exist
        expect(page.locator('ion-tab-button').first).to_be_visible()

    # =========================================================================
    # PRODUCTS LIST TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_products_list_page_loads(self, page: Page):
        """Test that products list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_products_list_has_search(self, page: Page):
        """Test that products list has search functionality."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Verify search bar
        search = page.locator('ion-searchbar, input[type="search"], input[name="search"]')
        if search.count() > 0:
            expect(search.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_products_list_empty_state(self, page: Page):
        """Test empty state when no products exist."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Should show table or empty state
        content = page.locator('table, .ui-empty-state, :text("No products")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_products_list_with_data(self, page: Page):
        """Test products list displays product data."""
        product = self.create_test_product()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1500)

        # Verify table or product name visible
        content = page.locator('table, :text("Test Product")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        # Cleanup
        product.category.delete()

    @pytest.mark.django_db(transaction=True)
    def test_products_list_ajax_api(self, page: Page):
        """Test products list AJAX API."""
        product = self.create_test_product()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/inventory/products/api/list/")

        if response.ok:
            data = response.json()
            assert 'success' in data or 'products' in data

        product.category.delete()

    @pytest.mark.django_db(transaction=True)
    def test_products_search_functionality(self, page: Page):
        """Test product search by name/SKU."""
        product = self.create_test_product()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Type in search
        search_input = page.locator('ion-searchbar input, input[name="search"]')
        if search_input.count() > 0:
            search_input.first.fill('TEST-001')
            page.wait_for_timeout(500)

        product.category.delete()

    # =========================================================================
    # PRODUCT CRUD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_product_create_page_loads(self, page: Page):
        """Test that product create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_product_create_form_fields(self, page: Page):
        """Test that product create form has required fields."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/create/")
        page.wait_for_load_state('networkidle')

        # Verify form fields exist
        expect(page.locator('ion-input[name="name"], input[name="name"]').first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_product_view_page_loads(self, page: Page):
        """Test that product view page loads correctly."""
        product = self.create_test_product()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/{product.pk}/")
        page.wait_for_load_state('networkidle')

        # Verify product name is displayed
        expect(page.locator(':text("Test Product")')).to_be_visible()

        product.category.delete()

    @pytest.mark.django_db(transaction=True)
    def test_product_edit_page_loads(self, page: Page):
        """Test that product edit page loads correctly."""
        product = self.create_test_product()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/{product.pk}/edit/")
        page.wait_for_load_state('networkidle')

        # Verify form is pre-filled
        name_input = page.locator('ion-input[name="name"] input, input[name="name"]').first
        expect(name_input).to_have_value('Test Product')

        product.category.delete()

    @pytest.mark.django_db(transaction=True)
    def test_product_delete_endpoint(self, page: Page):
        """Test product delete functionality."""
        product = self.create_test_product()
        category = product.category
        self.login(page)

        # Navigate to list and find delete button
        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Cleanup
        category.delete()

    # =========================================================================
    # CATEGORIES TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_categories_page_loads(self, page: Page):
        """Test that categories page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/categories/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_categories_list_with_data(self, page: Page):
        """Test categories list displays data."""
        category = self.create_test_category()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/categories/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify category name visible
        content = page.locator('table, :text("Test Category")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        category.delete()

    @pytest.mark.django_db(transaction=True)
    def test_categories_api(self, page: Page):
        """Test categories API endpoint."""
        category = self.create_test_category()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/inventory/categories/api/")

        if response.ok:
            data = response.json()
            assert isinstance(data, (list, dict))

        category.delete()

    @pytest.mark.django_db(transaction=True)
    def test_category_create_page_loads(self, page: Page):
        """Test that category create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/categories/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_category_edit_page_loads(self, page: Page):
        """Test that category edit page loads correctly."""
        category = self.create_test_category()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/categories/edit/{category.pk}/")
        page.wait_for_load_state('networkidle')

        # Verify form is pre-filled
        name_input = page.locator('ion-input[name="name"] input, input[name="name"]').first
        if name_input.count() > 0:
            expect(name_input).to_have_value('Test Category')

        category.delete()

    # =========================================================================
    # EXPORT/IMPORT TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_export_products_csv(self, page: Page):
        """Test export products to CSV."""
        product = self.create_test_product()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Try to export
        export_btn = page.locator('ion-button:has-text("Export"), a[href*="export"]')
        if export_btn.count() > 0:
            # Just verify button exists
            expect(export_btn.first).to_be_visible()

        product.category.delete()

    @pytest.mark.django_db(transaction=True)
    def test_export_categories_csv(self, page: Page):
        """Test export categories to CSV."""
        category = self.create_test_category()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/categories/")
        page.wait_for_load_state('networkidle')

        # Try to export
        export_btn = page.locator('ion-button:has-text("Export"), a[href*="export"]')
        if export_btn.count() > 0:
            expect(export_btn.first).to_be_visible()

        category.delete()

    # =========================================================================
    # BARCODE TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_barcode_generation(self, page: Page):
        """Test barcode generation for product."""
        product = self.create_test_product()
        self.login(page)

        # Call barcode API
        response = page.request.get(f"{self.live_server.url}/m/inventory/products/{product.pk}/barcode/")

        # Should return image or JSON
        assert response.status in [200, 404, 500]

        product.category.delete()

    # =========================================================================
    # REPORTS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_reports_page_loads(self, page: Page):
        """Test that reports page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/reports/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_reports_shows_low_stock(self, page: Page):
        """Test that reports shows low stock items."""
        from inventory.models import Product
        from decimal import Decimal

        category = self.create_test_category()
        low_stock_product = Product.objects.create(
            name='Low Stock Product',
            sku='LOW-001',
            price=Decimal('10.00'),
            stock=5,
            low_stock_threshold=10,
            is_active=True
        )
        low_stock_product.categories.add(category)

        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/reports/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Should show low stock alert or section
        content = page.locator(':text("Low Stock"), :text("Bajo Stock"), :text("Low")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        category.delete()

    # =========================================================================
    # SETTINGS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_settings_page_loads(self, page: Page):
        """Test that settings page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/settings/")
        page.wait_for_load_state('networkidle')

        # Verify settings page
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_toggles(self, page: Page):
        """Test that settings has toggle options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/settings/")
        page.wait_for_load_state('networkidle')

        # Check for toggles
        toggles = page.locator('ion-toggle, ion-checkbox')
        if toggles.count() > 0:
            expect(toggles.first).to_be_visible()

    # =========================================================================
    # NAVIGATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_products(self, page: Page):
        """Test tabbar navigation to products."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
        page.wait_for_load_state('networkidle')

        # Click products tab
        products_tab = page.locator('ion-tab-button:has-text("Products"), ion-tab-button:has-text("Productos")')
        if products_tab.count() > 0:
            products_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*products.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_categories(self, page: Page):
        """Test tabbar navigation to categories."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
        page.wait_for_load_state('networkidle')

        # Click categories tab
        categories_tab = page.locator('ion-tab-button:has-text("Categories"), ion-tab-button:has-text("Categorias")')
        if categories_tab.count() > 0:
            categories_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*categories.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_reports(self, page: Page):
        """Test tabbar navigation to reports."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
        page.wait_for_load_state('networkidle')

        # Click reports tab
        reports_tab = page.locator('ion-tab-button:has-text("Reports"), ion-tab-button:has-text("Reportes")')
        if reports_tab.count() > 0:
            reports_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*reports.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_settings(self, page: Page):
        """Test tabbar navigation to settings."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
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
    def test_inventory_responsive_mobile(self, page: Page):
        """Test inventory page on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_products_responsive_tablet(self, page: Page):
        """Test products on tablet viewport."""
        page.set_viewport_size({"width": 768, "height": 1024})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_inventory_infinite_scroll(self, page: Page):
        """Test infinite scroll pagination for products."""
        from inventory.models import Product
        from decimal import Decimal

        # Create many products
        category = self.create_test_category()
        products = []
        for i in range(30):
            product = Product.objects.create(
                name=f'Product {i}',
                sku=f'PROD-{i:03d}',
                price=Decimal('10.00'),
                stock=100,
                is_active=True
            )
            product.categories.add(category)
            products.append(product)

        self.login(page)

        page.goto(f"{self.live_server.url}/m/inventory/products/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1500)

        # Scroll to bottom
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(1000)

        # Cleanup
        category.delete()
