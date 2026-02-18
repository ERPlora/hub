"""
Unit tests for the setup wizard views.

Tests the multi-step HTMX wizard for initial Hub configuration.
URL patterns (app_name='setup'):
- setup:wizard -> /setup/
- setup:step -> /setup/step/<int:step>/
"""
import pytest
from decimal import Decimal
from django.urls import reverse


pytestmark = pytest.mark.unit


class TestWizardEntryPoint:
    """Tests for the setup wizard main entry point."""

    def test_wizard_loads_for_unconfigured_store(self, authenticated_client, unconfigured_store, hub_config):
        """Wizard page should load with 200 when store is not configured."""
        url = reverse('setup:wizard')
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_wizard_redirects_when_store_is_configured(self, authenticated_client, store_config, hub_config):
        """Wizard should redirect to home when store is already configured."""
        url = reverse('setup:wizard')
        response = authenticated_client.get(url)

        assert response.status_code == 302
        assert response.url == reverse('main:index')


class TestStep1Regional:
    """Tests for step 1 (regional settings)."""

    def test_step1_get_returns_regional_form(self, authenticated_client, unconfigured_store, hub_config):
        """GET step 1 should return the regional settings form."""
        url = reverse('setup:step', kwargs={'step': 1})
        response = authenticated_client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        # The full page should contain the wizard template
        assert 'language' in content.lower() or 'timezone' in content.lower()

    def test_step1_post_saves_language_and_timezone(self, authenticated_client, unconfigured_store, hub_config):
        """POST step 1 should save language and timezone to HubConfig."""
        from apps.configuration.models import HubConfig

        url = reverse('setup:step', kwargs={'step': 1})
        response = authenticated_client.post(url, {
            'language': 'es',
            'timezone': 'Europe/Madrid',
        })

        assert response.status_code == 200

        # Verify data was saved
        config = HubConfig.get_solo()
        assert config.language == 'es'
        assert config.timezone == 'Europe/Madrid'


class TestStep2Business:
    """Tests for step 2 (business information)."""

    def test_step2_get_returns_business_form(self, authenticated_client, unconfigured_store, hub_config):
        """GET step 2 should return the business info form."""
        url = reverse('setup:step', kwargs={'step': 2})
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_step2_post_saves_business_info(self, authenticated_client, unconfigured_store, hub_config):
        """POST step 2 should save business information to StoreConfig."""
        from apps.configuration.models import StoreConfig

        url = reverse('setup:step', kwargs={'step': 2})
        response = authenticated_client.post(url, {
            'business_name': 'My Test Shop',
            'business_address': '456 Commerce Ave',
            'vat_number': 'ES87654321B',
            'phone': '+34600111222',
            'email': 'shop@test.com',
        })

        assert response.status_code == 200

        # Verify data was saved
        config = StoreConfig.get_solo()
        assert config.business_name == 'My Test Shop'
        assert config.business_address == '456 Commerce Ave'
        assert config.vat_number == 'ES87654321B'

    def test_step2_post_fails_without_required_fields(self, authenticated_client, unconfigured_store, hub_config):
        """POST step 2 without required fields should re-render with errors."""
        url = reverse('setup:step', kwargs={'step': 2})
        response = authenticated_client.post(url, {
            'business_name': '',
            'business_address': '',
            'vat_number': '',
        })

        assert response.status_code == 200
        content = response.content.decode()
        # Should contain error indicators (re-rendered step 2 with errors)
        assert 'required' in content.lower() or 'error' in content.lower()


class TestStep3Tax:
    """Tests for step 3 (tax configuration)."""

    def test_step3_get_returns_tax_form(self, authenticated_client, unconfigured_store, hub_config):
        """GET step 3 should return the tax configuration form."""
        url = reverse('setup:step', kwargs={'step': 3})
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_step3_post_completes_setup_with_hx_redirect(self, authenticated_client, unconfigured_store, hub_config):
        """POST step 3 should complete setup and return HX-Redirect to home."""
        from apps.configuration.models import StoreConfig

        url = reverse('setup:step', kwargs={'step': 3})
        response = authenticated_client.post(url, {
            'tax_rate': '21',
            'tax_included': 'on',
        })

        assert response.status_code == 200
        assert response.get('HX-Redirect') == '/'

        # Verify store is now configured
        config = StoreConfig.get_solo()
        assert config.is_configured is True
        assert config.tax_rate == Decimal('21')
        assert config.tax_included is True


class TestFullWizardFlow:
    """Tests for the complete wizard flow from step 1 through step 3."""

    def test_full_wizard_flow(self, authenticated_client, unconfigured_store, hub_config):
        """Complete wizard flow: step 1 -> 2 -> 3 -> redirects to home."""
        from apps.configuration.models import HubConfig, StoreConfig

        # Step 1: Regional settings
        step1_url = reverse('setup:step', kwargs={'step': 1})
        response = authenticated_client.post(step1_url, {
            'language': 'en',
            'timezone': 'Europe/London',
        })
        assert response.status_code == 200

        # Verify step 1 saved
        hub = HubConfig.get_solo()
        assert hub.language == 'en'
        assert hub.timezone == 'Europe/London'

        # Step 2: Business info
        step2_url = reverse('setup:step', kwargs={'step': 2})
        response = authenticated_client.post(step2_url, {
            'business_name': 'Flow Test Store',
            'business_address': '789 Flow St',
            'vat_number': 'GB123456789',
            'phone': '+44700000000',
            'email': 'flow@test.com',
        })
        assert response.status_code == 200

        # Verify step 2 saved
        store = StoreConfig.get_solo()
        assert store.business_name == 'Flow Test Store'

        # Step 3: Tax config (final)
        step3_url = reverse('setup:step', kwargs={'step': 3})
        response = authenticated_client.post(step3_url, {
            'tax_rate': '20',
            'tax_included': 'on',
        })
        assert response.status_code == 200
        assert response.get('HX-Redirect') == '/'

        # Verify setup is complete
        store.refresh_from_db()
        assert store.is_configured is True

        # After setup, visiting wizard should redirect to home
        wizard_url = reverse('setup:wizard')
        response = authenticated_client.get(wizard_url)
        assert response.status_code == 302


class TestHtmxRendering:
    """Tests for HTMX partial vs full page rendering."""

    def test_htmx_request_returns_partial(self, authenticated_client, unconfigured_store, hub_config):
        """HTMX requests should return a partial (no DOCTYPE)."""
        url = reverse('setup:step', kwargs={'step': 1})
        response = authenticated_client.get(url, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()
        assert '<!DOCTYPE' not in content

    def test_non_htmx_request_returns_full_page(self, authenticated_client, unconfigured_store, hub_config):
        """Non-HTMX requests should return a full page (with DOCTYPE)."""
        url = reverse('setup:step', kwargs={'step': 1})
        response = authenticated_client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert '<!DOCTYPE' in content or '<!doctype' in content
