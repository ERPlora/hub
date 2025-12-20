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
        response = authenticated_client.get('/dashboard/')

        # Should redirect to wizard
        assert response.status_code == 302
        assert 'setup' in response.url or 'wizard' in response.url

    def test_wizard_shows_for_unconfigured_store(self, authenticated_client, unconfigured_store):
        """Test wizard page loads for unconfigured store."""
        response = authenticated_client.get('/setup/')

        assert response.status_code == 200
        assert b'Welcome' in response.content or b'ERPlora' in response.content

    def test_wizard_step1_save_business(self, authenticated_client, unconfigured_store):
        """Test saving business info in step 1."""
        response = authenticated_client.post('/setup/', {
            'action': 'save_business',
            'business_name': 'Test Business',
            'business_address': '123 Main St',
            'vat_number': 'ES12345678A',
            'phone': '+34 600 000 000',
            'email': 'test@example.com',
            'website': 'https://example.com'
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['next_step'] == 2

    def test_wizard_step2_save_tax(self, authenticated_client, store_config):
        """Test saving tax config in step 2."""
        response = authenticated_client.post('/setup/', {
            'action': 'save_tax',
            'tax_rate': '21',
            'tax_included': 'true'
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['next_step'] == 3

    def test_wizard_step3_save_receipt(self, authenticated_client, store_config):
        """Test saving receipt config in step 3."""
        response = authenticated_client.post('/setup/', {
            'action': 'save_receipt',
            'receipt_header': 'Welcome!',
            'receipt_footer': 'Thank you!'
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_wizard_finish(self, authenticated_client, store_config):
        """Test finishing the wizard."""
        response = authenticated_client.post('/setup/', {
            'action': 'finish'
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'redirect' in data
        assert '/dashboard/' in data['redirect']

    def test_wizard_skip_when_complete(self, authenticated_client, store_config):
        """Test skipping to finish when required fields are complete."""
        response = authenticated_client.post('/setup/', {
            'action': 'skip'
        })

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'redirect' in data

    def test_wizard_finish_fails_without_required(self, authenticated_client, unconfigured_store):
        """Test that finish fails without required fields."""
        response = authenticated_client.post('/setup/', {
            'action': 'finish'
        })

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False

    def test_configured_store_redirects_from_wizard(self, authenticated_client, store_config):
        """Test that configured store redirects away from wizard."""
        response = authenticated_client.get('/setup/')

        # Should redirect to dashboard
        assert response.status_code == 302
        assert 'dashboard' in response.url


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
