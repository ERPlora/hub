"""
Integration tests for Store Wizard.

Tests the multi-step HTMX wizard flow from unconfigured store to configured.
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
        assert b'ERPlora' in response.content

    def test_wizard_starts_at_step1(self, authenticated_client, unconfigured_store):
        """Test wizard starts at step 1 (regional settings)."""
        response = authenticated_client.get('/setup/')

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Regional Settings' in content or 'globe-outline' in content

    # =========================================================================
    # Step 1: Regional Settings
    # =========================================================================

    def test_step1_saves_language_and_timezone(self, authenticated_client, unconfigured_store):
        """Test step 1 POST saves language and timezone to HubConfig."""
        from apps.configuration.models import HubConfig

        response = authenticated_client.post('/setup/step/1/', {
            'language': 'es',
            'timezone': 'Europe/Madrid',
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200

        config = HubConfig.get_solo()
        assert config.language == 'es'
        assert config.timezone == 'Europe/Madrid'

    def test_step1_returns_step2_partial(self, authenticated_client, unconfigured_store):
        """Test step 1 POST returns step 2 content."""
        response = authenticated_client.post('/setup/step/1/', {
            'language': 'en',
            'timezone': 'UTC',
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Business Information' in content or 'business_name' in content

    # =========================================================================
    # Step 2: Business Information
    # =========================================================================

    def test_step2_saves_business_info(self, authenticated_client, unconfigured_store):
        """Test step 2 POST saves business data to StoreConfig."""
        from apps.configuration.models import StoreConfig

        response = authenticated_client.post('/setup/step/2/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
            'phone': '+34 600 000 000',
            'email': 'test@example.com',
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200

        config = StoreConfig.get_solo()
        assert config.business_name == 'Test Business'
        assert config.business_address == '123 Main St'
        assert config.vat_number == 'ES12345678A'
        assert config.phone == '+34 600 000 000'
        assert config.email == 'test@example.com'
        # Should NOT be configured yet (step 3 not done)
        assert config.is_configured is False

    def test_step2_returns_step3_partial(self, authenticated_client, unconfigured_store):
        """Test step 2 POST returns step 3 content."""
        response = authenticated_client.post('/setup/step/2/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Tax Configuration' in content or 'tax_rate' in content

    def test_step2_fails_without_business_name(self, authenticated_client, unconfigured_store):
        """Test that step 2 fails without business name."""
        response = authenticated_client.post('/setup/step/2/', {
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Business name is required' in content

    def test_step2_fails_without_address(self, authenticated_client, unconfigured_store):
        """Test that step 2 fails without address."""
        response = authenticated_client.post('/setup/step/2/', {
            'business_name': 'Test Business',
            'vat_number': 'ES12345678A',
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()
        assert 'Address is required' in content

    def test_step2_fails_without_vat_number(self, authenticated_client, unconfigured_store):
        """Test that step 2 fails without VAT number."""
        response = authenticated_client.post('/setup/step/2/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()
        assert 'VAT/Tax ID is required' in content

    # =========================================================================
    # Step 3: Tax Configuration
    # =========================================================================

    def test_step3_completes_setup(self, authenticated_client, unconfigured_store):
        """Test step 3 POST marks store as configured and redirects."""
        from apps.configuration.models import StoreConfig

        # Need to complete step 2 first (business info required)
        authenticated_client.post('/setup/step/2/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
        }, HTTP_HX_REQUEST='true')

        response = authenticated_client.post('/setup/step/3/', {
            'tax_rate': '21',
            'tax_included': 'on',
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        assert response.get('HX-Redirect') == '/home/'

        config = StoreConfig.get_solo()
        assert config.is_configured is True
        assert config.tax_rate == Decimal('21')
        assert config.tax_included is True

    def test_step3_defaults_tax_rate(self, authenticated_client, unconfigured_store):
        """Test that step 3 defaults tax rate to 21 if not provided."""
        from apps.configuration.models import StoreConfig

        response = authenticated_client.post('/setup/step/3/', {
        }, HTTP_HX_REQUEST='true')

        assert response.status_code == 200

        config = StoreConfig.get_solo()
        assert config.tax_rate == Decimal('21')

    # =========================================================================
    # Full wizard flow
    # =========================================================================

    def test_wizard_complete_flow(self, authenticated_client, unconfigured_store):
        """Test the complete multi-step wizard flow."""
        from apps.configuration.models import StoreConfig, HubConfig

        # Step 1: Regional settings
        response = authenticated_client.post('/setup/step/1/', {
            'language': 'es',
            'timezone': 'Europe/Madrid',
        }, HTTP_HX_REQUEST='true')
        assert response.status_code == 200

        # Step 2: Business info
        response = authenticated_client.post('/setup/step/2/', {
            'business_name': 'Test Business',
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
            'phone': '+34 600 000 000',
            'email': 'test@example.com',
        }, HTTP_HX_REQUEST='true')
        assert response.status_code == 200

        # Step 3: Tax config
        response = authenticated_client.post('/setup/step/3/', {
            'tax_rate': '10',
            'tax_included': 'on',
        }, HTTP_HX_REQUEST='true')
        assert response.status_code == 200
        assert response.get('HX-Redirect') == '/home/'

        # Verify all data saved
        hub = HubConfig.get_solo()
        assert hub.language == 'es'
        assert hub.timezone == 'Europe/Madrid'

        store = StoreConfig.get_solo()
        assert store.is_configured is True
        assert store.business_name == 'Test Business'
        assert store.business_address == '123 Main St'
        assert store.vat_number == 'ES12345678A'
        assert store.phone == '+34 600 000 000'
        assert store.email == 'test@example.com'
        assert store.tax_rate == Decimal('10')
        assert store.tax_included is True

    # =========================================================================
    # Navigation
    # =========================================================================

    def test_back_navigation_returns_partial(self, authenticated_client, unconfigured_store):
        """Test GET step with HX-Request returns partial."""
        response = authenticated_client.get('/setup/step/1/',
                                            HTTP_HX_REQUEST='true')
        assert response.status_code == 200
        content = response.content.decode()
        # Should return partial (no full HTML page wrapper)
        assert '<!DOCTYPE' not in content
        assert 'Regional Settings' in content or 'language' in content

    def test_direct_url_returns_full_page(self, authenticated_client, unconfigured_store):
        """Test GET step without HX-Request returns full page."""
        response = authenticated_client.get('/setup/step/2/')
        assert response.status_code == 200
        content = response.content.decode()
        # Should return full page
        assert '<!DOCTYPE' in content or '<html' in content

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
