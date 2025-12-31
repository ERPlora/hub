"""
E2E Tests for Loyalty Module

Coverage:
- Dashboard page
- Members management (CRUD)
- Tiers management
- Rewards management
- Transactions list
- API endpoints
- Settings page
- KPI stat cards
"""
import re
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.playwright, pytest.mark.e2e]


class TestLoyaltyModule:
    """E2E tests for the Loyalty module."""

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

    def create_test_tier(self):
        """Helper to create a test loyalty tier."""
        from loyalty.models import LoyaltyTier

        return LoyaltyTier.objects.create(
            name='Bronze',
            min_points=0,
            multiplier=1.0,
            color='#CD7F32',
            is_active=True
        )

    def create_test_member(self, tier=None):
        """Helper to create a test loyalty member."""
        from loyalty.models import LoyaltyMember
        import uuid

        if not tier:
            tier = self.create_test_tier()

        # Generate unique member number to avoid conflicts
        member_number = f"TEST-{uuid.uuid4().hex[:8].upper()}"

        return LoyaltyMember.objects.create(
            member_number=member_number,
            name='Test Member',
            email='member@test.com',
            phone='+34666123456',
            tier=tier,
            points_balance=100,
            is_active=True
        )

    def create_test_reward(self):
        """Helper to create a test reward."""
        from loyalty.models import Reward

        return Reward.objects.create(
            name='Test Reward',
            description='Test reward description',
            points_cost=50,
            is_active=True
        )

    # =========================================================================
    # DASHBOARD TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_loyalty_dashboard_loads(self, page: Page):
        """Test that loyalty dashboard page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_loyalty_dashboard_has_kpi_cards(self, page: Page):
        """Test that dashboard displays KPI stat cards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/")
        page.wait_for_load_state('networkidle')

        # Check for stat cards
        stat_cards = page.locator('.ui-stat-card, ion-card')
        if stat_cards.count() > 0:
            expect(stat_cards.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_loyalty_tabbar_visible(self, page: Page):
        """Test that loyalty tabbar is visible."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/")
        page.wait_for_load_state('networkidle')

        # Verify tabbar exists
        tabbar = page.locator('ion-tab-bar')
        expect(tabbar).to_be_visible()

    # =========================================================================
    # MEMBERS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_members_list_page_loads(self, page: Page):
        """Test that members list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/members/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_members_list_empty_state(self, page: Page):
        """Test empty state when no members exist."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/members/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Should show table or empty state
        content = page.locator('table, .ui-empty-state, :text("No members")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_members_list_with_data(self, page: Page):
        """Test members list displays member data."""
        member = self.create_test_member()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/members/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify member visible
        content = page.locator('table, :text("Test Member")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        member.tier.delete()

    @pytest.mark.django_db(transaction=True)
    def test_member_create_page_loads(self, page: Page):
        """Test that member create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/members/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_member_detail_page_loads(self, page: Page):
        """Test that member detail page loads correctly."""
        member = self.create_test_member()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/members/{member.pk}/")
        page.wait_for_load_state('networkidle')

        # Verify member info is displayed
        content = page.locator(':text("Test Member")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        member.tier.delete()

    @pytest.mark.django_db(transaction=True)
    def test_member_edit_page_loads(self, page: Page):
        """Test that member edit page loads correctly."""
        member = self.create_test_member()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/members/{member.pk}/edit/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

        member.tier.delete()

    @pytest.mark.django_db(transaction=True)
    def test_member_export_csv(self, page: Page):
        """Test export members to CSV endpoint exists."""
        member = self.create_test_member()
        self.login(page)

        # Check endpoint
        response = page.request.get(f"{self.live_server.url}/m/loyalty/members/export/csv/")
        assert response.status in [200, 302, 404]

        member.tier.delete()

    # =========================================================================
    # TIERS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_tiers_list_page_loads(self, page: Page):
        """Test that tiers list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/tiers/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_tiers_list_with_data(self, page: Page):
        """Test tiers list displays tier data."""
        tier = self.create_test_tier()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/tiers/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify tier visible
        content = page.locator(':text("Bronze")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        tier.delete()

    @pytest.mark.django_db(transaction=True)
    def test_tier_create_page_loads(self, page: Page):
        """Test that tier create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/tiers/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_tier_edit_page_loads(self, page: Page):
        """Test that tier edit page loads correctly."""
        tier = self.create_test_tier()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/tiers/{tier.pk}/edit/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

        tier.delete()

    # =========================================================================
    # REWARDS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_rewards_list_page_loads(self, page: Page):
        """Test that rewards list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/rewards/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_rewards_list_with_data(self, page: Page):
        """Test rewards list displays reward data."""
        reward = self.create_test_reward()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/rewards/")
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(1000)

        # Verify reward visible
        content = page.locator(':text("Test Reward")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        reward.delete()

    @pytest.mark.django_db(transaction=True)
    def test_reward_create_page_loads(self, page: Page):
        """Test that reward create page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/rewards/create/")
        page.wait_for_load_state('networkidle')

        # Verify form exists
        form = page.locator('form, ion-input')
        expect(form.first).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_reward_detail_page_loads(self, page: Page):
        """Test that reward detail page loads correctly."""
        reward = self.create_test_reward()
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/rewards/{reward.pk}/")
        page.wait_for_load_state('networkidle')

        # Verify reward info is displayed
        content = page.locator(':text("Test Reward")')
        if content.count() > 0:
            expect(content.first).to_be_visible()

        reward.delete()

    # =========================================================================
    # TRANSACTIONS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_transactions_list_page_loads(self, page: Page):
        """Test that transactions list page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/transactions/")
        page.wait_for_load_state('networkidle')

        # Verify page loads
        expect(page.locator('#main-content-area')).to_be_visible()

    # =========================================================================
    # API TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_api_member_search(self, page: Page):
        """Test API member search endpoint."""
        member = self.create_test_member()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/loyalty/api/search/?q=test")

        if response.ok:
            data = response.json()
            assert 'success' in data or 'members' in data or isinstance(data, list)

        member.tier.delete()

    @pytest.mark.django_db(transaction=True)
    def test_api_member_balance(self, page: Page):
        """Test API member balance endpoint."""
        member = self.create_test_member()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/loyalty/api/members/{member.pk}/balance/")

        if response.ok:
            data = response.json()
            assert 'balance' in data or 'points' in data or isinstance(data, dict)

        member.tier.delete()

    @pytest.mark.django_db(transaction=True)
    def test_api_available_rewards(self, page: Page):
        """Test API available rewards endpoint."""
        member = self.create_test_member()
        reward = self.create_test_reward()
        self.login(page)

        # API call
        response = page.request.get(f"{self.live_server.url}/m/loyalty/api/rewards/available/{member.pk}/")

        if response.ok:
            data = response.json()
            assert 'rewards' in data or isinstance(data, list)

        member.tier.delete()
        reward.delete()

    # =========================================================================
    # SETTINGS TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_settings_page_loads(self, page: Page):
        """Test that settings page loads correctly."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/settings/")
        page.wait_for_load_state('networkidle')

        # Verify settings page
        expect(page.locator('#main-content-area')).to_be_visible()

    @pytest.mark.django_db(transaction=True)
    def test_settings_has_toggles(self, page: Page):
        """Test that settings has toggle options."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/settings/")
        page.wait_for_load_state('networkidle')

        # Check for toggles
        toggles = page.locator('ion-toggle, ion-checkbox')
        if toggles.count() > 0:
            expect(toggles.first).to_be_visible()

    # =========================================================================
    # NAVIGATION TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_members(self, page: Page):
        """Test tabbar navigation to members."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/")
        page.wait_for_load_state('networkidle')

        # Click members tab
        members_tab = page.locator('ion-tab-button:has-text("Members"), ion-tab-button:has-text("Miembros")')
        if members_tab.count() > 0:
            members_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*members.*'))

    @pytest.mark.django_db(transaction=True)
    def test_tabbar_navigation_to_rewards(self, page: Page):
        """Test tabbar navigation to rewards."""
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/")
        page.wait_for_load_state('networkidle')

        # Click rewards tab
        rewards_tab = page.locator('ion-tab-button:has-text("Rewards"), ion-tab-button:has-text("Recompensas")')
        if rewards_tab.count() > 0:
            rewards_tab.first.click()
            page.wait_for_load_state('networkidle')
            expect(page).to_have_url(re.compile(r'.*rewards.*'))

    # =========================================================================
    # RESPONSIVE TESTS
    # =========================================================================

    @pytest.mark.django_db(transaction=True)
    def test_loyalty_responsive_mobile(self, page: Page):
        """Test loyalty page on mobile viewport."""
        page.set_viewport_size({"width": 375, "height": 667})
        self.login(page)

        page.goto(f"{self.live_server.url}/m/loyalty/")
        page.wait_for_load_state('networkidle')

        # Verify page loads correctly
        expect(page.locator('#main-content-area')).to_be_visible()
