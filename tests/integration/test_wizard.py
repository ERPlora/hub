"""
Integration tests for Store Wizard.

Tests the full wizard flow from unconfigured store to configured.
"""
import pytest
from decimal import Decimal

pytestmark = pytest.mark.integration


class TestWizardFlow:
    """Tests for the store wizard configuration flow."""

    def test_wizard_redirects_when_not_configured(self, authenticated_client, unconfigured_store):
        """Test that unconfigured store redirects to wizard."""
        response = authenticated_client.get('/home/')

        # Should redirect to wizard
        assert response.status_code == 302
        assert 'setup' in response.url or 'wizard' in response.url

    def test_wizard_shows_for_unconfigured_store(self, authenticated_client, unconfigured_store):
        """Test wizard page loads for unconfigured store."""
        response = authenticated_client.get('/setup/')

        assert response.status_code == 200
        assert b'Welcome' in response.content or b'ERPlora' in response.content

    def test_wizard_complete_form_submission(self, authenticated_client, unconfigured_store):
        """Test submitting the complete wizard form with all required fields."""
        from apps.configuration.models import StoreConfig

        response = authenticated_client.post('/setup/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
            'phone': '+34 600 000 000',
            'email': 'test@example.com',
            'tax_rate': '21',
            'tax_included': 'on'
        })

        # Success returns 200 with HX-Redirect header
        assert response.status_code == 200
        assert response.get('HX-Redirect') == '/home/'

        # Verify config was saved
        config = StoreConfig.get_solo()
        assert config.is_configured is True
        assert config.business_name == 'Test Business'
        assert config.business_address == '123 Main St'
        assert config.vat_number == 'ES12345678A'

    def test_wizard_fails_without_business_name(self, authenticated_client, unconfigured_store):
        """Test that wizard fails without business name."""
        response = authenticated_client.post('/setup/', {
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
        })

        # Should return 400 with error HTML
        assert response.status_code == 400
        assert b'Business name is required' in response.content

    def test_wizard_fails_without_address(self, authenticated_client, unconfigured_store):
        """Test that wizard fails without address."""
        response = authenticated_client.post('/setup/', {
            'business_name': 'Test Business',
            'vat_number': 'ES12345678A',
        })

        assert response.status_code == 400
        assert b'Address is required' in response.content

    def test_wizard_fails_without_vat_number(self, authenticated_client, unconfigured_store):
        """Test that wizard fails without VAT number."""
        response = authenticated_client.post('/setup/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
        })

        assert response.status_code == 400
        assert b'VAT/Tax ID is required' in response.content

    def test_wizard_saves_optional_fields(self, authenticated_client, unconfigured_store):
        """Test that wizard saves optional fields correctly."""
        from apps.configuration.models import StoreConfig

        response = authenticated_client.post('/setup/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
            'phone': '+34 600 000 000',
            'email': 'test@example.com',
            'tax_rate': '10',
            'tax_included': 'on'
        })

        assert response.status_code == 200

        config = StoreConfig.get_solo()
        assert config.phone == '+34 600 000 000'
        assert config.email == 'test@example.com'
        assert config.tax_rate == 10
        assert config.tax_included is True

    def test_wizard_defaults_tax_rate(self, authenticated_client, unconfigured_store):
        """Test that wizard defaults tax rate to 21 if not provided."""
        from apps.configuration.models import StoreConfig

        response = authenticated_client.post('/setup/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
        })

        assert response.status_code == 200

        config = StoreConfig.get_solo()
        assert config.tax_rate == 21

    def test_configured_store_redirects_from_wizard(self, client, db):
        """Test that configured store redirects away from wizard."""
        from apps.accounts.models import LocalUser
        from apps.configuration.models import StoreConfig

        # Configure store
        store_config = StoreConfig.get_solo()
        store_config.is_configured = True
        store_config.business_name = 'Test Store'
        store_config.save()

        # Create and login user
        user = LocalUser.objects.create(
            name='Test User',
            email='test@example.com',
            role='admin',
            is_active=True
        )
        user.set_pin('1234')

        session = client.session
        session['local_user_id'] = str(user.id)
        session['user_name'] = user.name
        session['user_email'] = user.email
        session['user_role'] = user.role
        session.save()

        response = client.get('/setup/')

        # Should redirect to home
        assert response.status_code == 302
        assert 'home' in response.url


class TestMiddleware:
    """Tests for StoreConfigCheckMiddleware."""

    def test_middleware_allows_exempt_paths(self, authenticated_client, unconfigured_store):
        """Test that exempt paths are not redirected."""
        # API endpoints should be exempt
        response = authenticated_client.get('/api/v1/system/health/')

        # Should not redirect (200 or some other response, not 302 to wizard)
        assert response.status_code != 302 or 'setup' not in response.get('Location', '')

    def test_middleware_allows_static_files(self, authenticated_client, unconfigured_store):
        """Test that static files are not redirected."""
        response = authenticated_client.get('/static/css/test.css')

        # Should return 404 (file not found) not redirect to wizard
        assert response.status_code == 404 or response.status_code == 200
