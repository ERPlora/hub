"""
End-to-end tests for complete user flows.

Tests full scenarios from login to using features.
"""
import pytest
from decimal import Decimal

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


class TestNewUserSetup:
    """E2E tests for new user setup flow."""

    def test_complete_setup_flow(self, client, db):
        """Test complete flow from first login to configured store."""
        from apps.accounts.models import LocalUser
        from apps.configuration.models import StoreConfig

        # Ensure StoreConfig is unconfigured initially
        store_config = StoreConfig.get_solo()
        store_config.is_configured = False
        store_config.business_name = ''
        store_config.save()

        # 1. Create admin user (first run scenario)
        user = LocalUser.objects.create(
            name='Admin User',
            email='admin@example.com',
            role='admin',
            pin_hash='',
            is_active=True
        )
        user.set_pin('1234')

        # 2. Login
        session = client.session
        session['local_user_id'] = str(user.id)  # Convert UUID to string
        session['user_name'] = user.name
        session['user_email'] = user.email
        session['user_role'] = user.role
        session.save()

        # 3. Access home - should redirect to wizard
        response = client.get('/home/', follow=True)
        # Either loads wizard or redirects to setup
        assert response.status_code == 200

        # 4. Complete wizard (single form with HTMX)
        response = client.post('/setup/', {
            'business_name': 'My New Store',
            'business_address': '456 Commerce Ave',
            'vat_number': 'ES98765432B',
            'phone': '+34 611 222 333',
            'email': 'store@example.com',
            'tax_rate': '21',
            'tax_included': 'on'
        })
        # Success returns 200 with HX-Redirect header
        assert response.status_code == 200
        assert response.get('HX-Redirect') == '/home/'

        # 5. Verify store is configured
        store_config = StoreConfig.get_solo()
        assert store_config.is_configured is True
        assert store_config.business_name == 'My New Store'
        assert store_config.tax_rate == 21


class TestConfigurationFlow:
    """E2E tests for configuration management."""

    def test_change_currency_and_verify(self, authenticated_client, hub_config, store_config):
        """Test changing currency and verify it reflects in system."""
        import json

        # 1. Change currency via API
        response = authenticated_client.patch(
            '/api/v1/config/hub/',
            data=json.dumps({'currency': 'USD'}),
            content_type='application/json'
        )
        assert response.status_code == 200

        # 2. Verify currency changed
        from apps.configuration.models import HubConfig
        HubConfig._clear_cache()
        updated_config = HubConfig.get_solo()
        assert updated_config.currency == 'USD'

        # 3. Verify currency service reflects change
        from apps.core.services import get_currency
        assert get_currency() == 'USD'

    def test_change_tax_and_verify_calculations(self, authenticated_client, store_config):
        """Test changing tax rate and verify calculations."""
        import json

        # 1. Change tax rate
        response = authenticated_client.patch(
            '/api/v1/config/store/',
            data=json.dumps({'tax_rate': '10.00'}),
            content_type='application/json'
        )
        assert response.status_code == 200

        # 2. Verify tax service uses new rate
        from apps.configuration.models import StoreConfig
        StoreConfig._clear_cache()

        from apps.core.services import calculate_tax
        net, tax, gross = calculate_tax(110, tax_included=True)

        assert net == Decimal('100.00')
        assert tax == Decimal('10.00')


class TestModuleFlow:
    """E2E tests for module management."""

    def test_view_modules_list(self, authenticated_client, store_config):
        """Test viewing installed modules."""
        response = authenticated_client.get('/store/')

        assert response.status_code == 200
        # Should show modules page
        assert b'Modules' in response.content or b'modules' in response.content

    def test_access_active_module(self, authenticated_client, store_config):
        """Test accessing an active module (inventory)."""
        response = authenticated_client.get('/modules/inventory/')

        # Should either work (200) or redirect to another page
        # If module is active, should be accessible
        assert response.status_code in [200, 302]


class TestDashboardFlow:
    """E2E tests for dashboard functionality."""

    def test_home_loads(self, authenticated_client, store_config):
        """Test home page loads for configured store."""
        response = authenticated_client.get('/home/')

        assert response.status_code == 200
        # Should contain dashboard content
        assert len(response.content) > 0

    def test_settings_page_loads(self, authenticated_client, store_config):
        """Test settings page loads."""
        response = authenticated_client.get('/settings/')

        assert response.status_code == 200
