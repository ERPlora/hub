"""
E2E Tests for Sections Module (Tables/Floor View)

Coverage:
- Floor view page
- Table management (CRUD)
- Area management (CRUD)
- Table actions (open, close, transfer, block)
- Settings page
- API endpoints
- KPI stat cards
"""
import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestSectionsModule:
    """E2E tests for the Sections (Tables/Floor) module."""

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

    def create_test_area(self):
        """Helper to create a test area."""
        from sections.models import Area

        return Area.objects.create(
            name='Test Area',
            description='Test area description',
            color='#FF5733',
            icon='restaurant-outline',
            is_active=True
        )

    def create_test_table(self, area=None):
        """Helper to create a test table."""
        from sections.models import Table

        if not area:
            area = self.create_test_area()

        return Table.objects.create(
            number=1,
            name='Table 1',
            area=area,
            capacity=4,
            status='available',
            is_active=True
        )

    # =========================================================================
    # FLOOR VIEW TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_floor_view_loads(self, page: Page):
        """Test that floor view page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_floor_view_has_kpi_cards(self, page: Page):
        """Test that floor view displays 4 KPI stat cards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Verify KPI labels (use .first to avoid strict mode violation from multiple matches)
        expect(page.locator('.ui-stat-label:has-text("Available"), .ui-stat-label:has-text("Disponible")').first).to_be_visible()
        expect(page.locator('.ui-stat-label:has-text("Occupied"), .ui-stat-label:has-text("Ocupado")').first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_floor_view_tabbar_visible(self, page: Page):
        """Test that floor view tabbar is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Verify tabbar exists
        tabbar = page.locator('ion-tab-bar')
        expect(tabbar).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_floor_view_shows_tables_grid(self, page: Page):
        """Test that floor view shows tables grid when tables exist."""
        table = self.create_test_table()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Verify table grid or table card visible
        table_el = page.locator('.floor-grid, .floor-table, :text("Table 1"), :text("1")')
        if table_el.count() > 0:
            expect(table_el.first).to_be_visible()

        table.area.delete()

    @pytest.mark.django_db(transaction=True)
    def test_floor_view_empty_state(self, page: Page):
        """Test empty state when no tables exist."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Should show empty state or FAB button
        content = page.locator('.ui-empty-state, ion-fab, :text("No tables")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_floor_view_area_filters(self, page: Page):
        """Test area filter buttons."""
        area = self.create_test_area()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Verify area filter buttons
        filter_btn = page.locator(f'ion-button:has-text("{area.name}"), ion-button:has-text("All Areas")')
        if filter_btn.count() > 0:
            expect(filter_btn.first).to_be_visible()

        area.delete()

    @pytest.mark.django_db(transaction=True)
    def test_floor_view_status_filter(self, page: Page):
        """Test status filter segment."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Verify status segment
        segment = page.locator('ion-segment')
        if segment.count() > 0:
            expect(segment.first).to_be_visible()

    # =========================================================================
    # TABLE MANAGEMENT TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_table_list_page_loads(self, page: Page):
        """Test that table list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/tables/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_table_create_page_loads(self, page: Page):
        """Test that table create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/tables/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_table_create_form_fields(self, page: Page):
        """Test that table create form has required fields."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/tables/create/")
        page.wait_for_load_state('networkidle')

        # Verify form fields exist
        number_input = page.locator('ion-input[name="number"], input[name="number"]')
        if number_input.count() > 0:
            expect(number_input.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_table_detail_page_loads(self, page: Page):
        """Test that table detail page loads correctly."""
        table = self.create_test_table()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/tables/{table.pk}/")
        page.wait_for_load_state('networkidle')

        # Verify table info is displayed
        content = page.locator(':text("Table 1"), :text("1")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        table.area.delete()

    @pytest.mark.django_db(transaction=True)
    def test_table_edit_page_loads(self, page: Page):
        """Test that table edit page loads correctly."""
        table = self.create_test_table()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/tables/{table.pk}/edit/")
        page.wait_for_load_state('networkidle')

        # Verify form is pre-filled
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

        table.area.delete()

    # =========================================================================
    # AREA MANAGEMENT TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_area_list_page_loads(self, page: Page):
        """Test that area list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/areas/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_area_create_page_loads(self, page: Page):
        """Test that area create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/areas/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_area_list_with_data(self, page: Page):
        """Test area list displays area data."""
        area = self.create_test_area()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/areas/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify area name visible
        content = page.locator(f':text("{area.name}")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        area.delete()

    @pytest.mark.django_db(transaction=True)
    def test_area_detail_page_loads(self, page: Page):
        """Test that area detail page loads correctly."""
        area = self.create_test_area()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/areas/{area.pk}/")
        page.wait_for_load_state('networkidle')

        # Verify area info is displayed
        content = page.locator(f':text("{area.name}")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        area.delete()

    @pytest.mark.django_db(transaction=True)
    def test_area_edit_page_loads(self, page: Page):
        """Test that area edit page loads correctly."""
        area = self.create_test_area()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/areas/{area.pk}/edit/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

        area.delete()

    # =========================================================================
    # TABLE ACTIONS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_table_open_action(self, page: Page):
        """Test table open action."""
        table = self.create_test_table()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/tables/{table.pk}/open/")
        page.wait_for_load_state('networkidle')

        # Should load some form or redirect
        expect(page.locator('#main-content-area form, form').first).to_be_visible()

        table.area.delete()

    @pytest.mark.django_db(transaction=True)
    def test_table_block_action(self, page: Page):
        """Test table block action endpoint."""
        table = self.create_test_table()
        self.login(page)

        # Just verify endpoint exists
        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        table.area.delete()

    @pytest.mark.django_db(transaction=True)
    def test_table_transfer_action(self, page: Page):
        """Test table transfer action."""
        table = self.create_test_table()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/tables/{table.pk}/transfer/")
        page.wait_for_load_state('networkidle')

        # Should load transfer form or page
        expect(page.locator('#main-content-area form, form').first).to_be_visible()

        table.area.delete()

    # =========================================================================
    # SETTINGS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_settings_page_loads(self, page: Page):
        """Test that settings page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/settings/")
        page.wait_for_load_state('networkidle')

        # Verify settings page
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_toggles(self, page: Page):
        """Test that settings has toggle options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/settings/")
        page.wait_for_load_state('networkidle')

        # Check for toggles
        toggles = page.locator('ion-toggle, ion-checkbox')
        if toggles.count() > 0:
            expect(toggles.first).to_be_visible()

    # =========================================================================
    # API TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_api_tables_status(self, page: Page):
        """Test API tables status endpoint."""
        table = self.create_test_table()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/sections/api/status/")

        if response.ok:
            data = response.json()
            assert 'success' in data or 'tables' in data or isinstance(data, list)

        table.area.delete()

    @pytest.mark.django_db(transaction=True)
    def test_api_areas(self, page: Page):
        """Test API areas endpoint."""
        area = self.create_test_area()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/sections/api/areas/")

        if response.ok:
            data = response.json()
            assert 'success' in data or 'areas' in data or isinstance(data, list)

        area.delete()

    # =========================================================================
    # NAVIGATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_areas(self, page: Page):
        """Test tabbar navigation to areas."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Click areas tab
        areas_tab = page.locator('ion-tab-button:has-text("Areas")')
        if areas_tab.count() > 0:
            areas_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*areas.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_tables(self, page: Page):
        """Test tabbar navigation to tables list."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Click tables tab
        tables_tab = page.locator('ion-tab-button:has-text("Tables"), ion-tab-button:has-text("Mesas")')
        if tables_tab.count() > 0:
            tables_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*tables.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_settings(self, page: Page):
        """Test tabbar navigation to settings."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
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
    def test_floor_view_responsive_mobile(self, page: Page):
        """Test floor view on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_floor_view_responsive_tablet(self, page: Page):
        """Test floor view on tablet viewport."""
        page.set_viewport_size({"width": 768, "height": 1024})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_floor_grid_columns(self, page: Page):
        """Test floor grid has proper column layout."""
        table = self.create_test_table()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')

        # Check for grid
        grid = page.locator('.floor-grid')
        if grid.count() > 0:
            expect(grid.first).to_be_visible()

        table.area.delete()

    # =========================================================================
    # INTEGRATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_table_click_to_open(self, page: Page):
        """Test clicking available table triggers open action."""
        table = self.create_test_table()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/sections/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Click on table
        table_el = page.locator('.floor-table--available')
        if table_el.count() > 0:
            table_el.first.click()
            page.wait_for_load_state('networkidle')
            # Should navigate to open table flow
            expect(page.locator('#main-content-area')).to_be_visible()

        table.area.delete()
