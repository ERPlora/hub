"""
Unit tests for the module install flow.

Tests module install, activate, deactivate, and marketplace fetch API endpoints.
URL patterns (app_name='mymodules'):
- mymodules:api_install -> /modules/api/marketplace/install/ (POST)
- mymodules:api_activate -> /modules/api/activate/<module_id>/ (POST)
- mymodules:api_deactivate -> /modules/api/deactivate/<module_id>/ (POST)
- mymodules:api_fetch -> /modules/api/marketplace/ (GET)
"""
import io
import json
import zipfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from django.urls import reverse
from django.conf import settings as django_settings


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_module_zip(module_slug='test_module'):
    """Create an in-memory zip file simulating a module package."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f'{module_slug}/__init__.py', '')
        zf.writestr(f'{module_slug}/module.py', f"MODULE_ID = '{module_slug}'\nMODULE_NAME = 'Test Module'\n")
        zf.writestr(f'{module_slug}/views.py', '')
        zf.writestr(f'{module_slug}/urls.py', 'urlpatterns = []\n')
    buf.seek(0)
    return buf


def _mock_download_response(module_slug='test_module'):
    """Create a mock requests response that streams a module zip."""
    zip_buf = _create_module_zip(module_slug)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.iter_content = MagicMock(return_value=[zip_buf.read()])
    return mock_response


def _mock_cloud_modules_api():
    """Return a mock Cloud API modules list response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'results': [
            {
                'id': 'mod-1',
                'name': 'Inventory',
                'slug': 'inventory',
                'description': 'Stock management',
                'category': 'operations',
                'module_type': 'free',
                'price': 0,
            },
        ]
    }
    return mock_response


class TestInstallFromMarketplace:
    """Tests for the install_from_marketplace API endpoint."""

    @patch('apps.modules_runtime.loader.module_loader')
    @patch('apps.system.modules.views.requests.get')
    def test_install_from_marketplace(self, mock_get, mock_loader, authenticated_client, hub_config, tmp_path):
        """Install from marketplace should download, extract, and register module."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        # Use tmp_path as MODULES_DIR
        mock_get.return_value = _mock_download_response('new_module')
        mock_loader.load_module = MagicMock()

        with patch.object(django_settings, 'MODULES_DIR', str(tmp_path)):
            url = reverse('mymodules:api_install')
            response = authenticated_client.post(
                url,
                data=json.dumps({
                    'module_slug': 'new_module',
                    'download_url': 'https://cloud.erplora.com/api/modules/new_module/download/',
                }),
                content_type='application/json',
            )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    @patch('apps.modules_runtime.loader.module_loader')
    @patch('apps.system.modules.views.requests.get')
    def test_http_to_https_normalization(self, mock_get, mock_loader, authenticated_client, hub_config, tmp_path):
        """Download URLs should be normalized from http:// to https://."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        mock_get.return_value = _mock_download_response('secure_module')
        mock_loader.load_module = MagicMock()

        with patch.object(django_settings, 'MODULES_DIR', str(tmp_path)):
            url = reverse('mymodules:api_install')
            response = authenticated_client.post(
                url,
                data=json.dumps({
                    'module_slug': 'secure_module',
                    'download_url': 'http://cloud.erplora.com/api/modules/secure_module/download/',
                }),
                content_type='application/json',
            )

        assert response.status_code == 200

        # Verify the request was made with https://
        actual_url = mock_get.call_args[0][0]
        assert actual_url.startswith('https://')

    @patch('apps.system.modules.views.requests.get')
    def test_install_fails_gracefully_on_cloud_error(self, mock_get, authenticated_client, hub_config, tmp_path):
        """Install should fail gracefully when Cloud returns an error."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        # Simulate a download failure
        import requests as real_requests
        mock_get.side_effect = real_requests.exceptions.ConnectionError('Cloud unreachable')

        with patch.object(django_settings, 'MODULES_DIR', str(tmp_path)):
            url = reverse('mymodules:api_install')
            response = authenticated_client.post(
                url,
                data=json.dumps({
                    'module_slug': 'failing_module',
                    'download_url': 'https://cloud.erplora.com/api/modules/failing_module/download/',
                }),
                content_type='application/json',
            )

        # Should return error, not crash
        assert response.status_code in (200, 400, 500)
        data = response.json()
        assert data['success'] is False

    def test_install_requires_authentication(self, client, db, store_config):
        """Install endpoint should require authentication (redirects to login)."""
        url = reverse('mymodules:api_install')
        response = client.post(
            url,
            data=json.dumps({
                'module_slug': 'test_module',
                'download_url': 'https://cloud.erplora.com/download/',
            }),
            content_type='application/json',
        )

        assert response.status_code == 302
        assert '/login/' in response.url


class TestModuleActivateDeactivate:
    """Tests for module activate and deactivate endpoints."""

    def test_module_activate(self, authenticated_client, hub_config, tmp_path):
        """Activating a disabled module should rename the folder."""
        # Create a disabled module folder (_test_mod)
        disabled_dir = tmp_path / '_test_mod'
        disabled_dir.mkdir()
        (disabled_dir / '__init__.py').write_text('')

        with patch.object(django_settings, 'MODULES_DIR', str(tmp_path)):
            with patch('apps.system.modules.views._trigger_server_reload'):
                url = reverse('mymodules:api_activate', kwargs={'module_id': 'test_mod'})
                response = authenticated_client.post(url)

        # The endpoint returns either JSON or HTMX reload HTML
        assert response.status_code == 200

        # The disabled folder should have been renamed to active
        assert (tmp_path / 'test_mod').exists() or not (tmp_path / '_test_mod').exists()

    def test_module_deactivate(self, authenticated_client, hub_config, tmp_path):
        """Deactivating an active module should rename the folder."""
        # Create an active module folder
        active_dir = tmp_path / 'test_mod'
        active_dir.mkdir()
        (active_dir / '__init__.py').write_text('')

        with patch.object(django_settings, 'MODULES_DIR', str(tmp_path)):
            with patch('apps.system.modules.views._trigger_server_reload'):
                url = reverse('mymodules:api_deactivate', kwargs={'module_id': 'test_mod'})
                response = authenticated_client.post(url)

        assert response.status_code == 200

        # The active folder should have been renamed to disabled
        assert (tmp_path / '_test_mod').exists() or not (tmp_path / 'test_mod').exists()


class TestFetchMarketplace:
    """Tests for the fetch_marketplace API endpoint."""

    @patch('apps.system.modules.views.requests.get')
    def test_fetch_marketplace_with_mock_response(self, mock_get, authenticated_client, hub_config):
        """Fetch marketplace should proxy Cloud API and return modules."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        mock_get.side_effect = [
            _mock_cloud_modules_api(),
            MagicMock(status_code=200, json=MagicMock(return_value=[])),  # categories
            MagicMock(status_code=200, json=MagicMock(return_value=[])),  # industries
        ]

        url = reverse('mymodules:api_fetch')
        response = authenticated_client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert 'modules' in data
        assert len(data['modules']) > 0

    def test_fetch_marketplace_requires_authentication(self, client, db, store_config):
        """Fetch marketplace should require authentication (redirects to login)."""
        url = reverse('mymodules:api_fetch')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url
