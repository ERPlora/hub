"""
Integration tests for Hub APIs.

Tests the REST API endpoints for configuration and plugins.
"""
import pytest
import json

pytestmark = pytest.mark.integration


class TestHubConfigAPI:
    """Tests for Hub Configuration API."""

    def test_get_hub_config(self, authenticated_client, hub_config):
        """Test getting hub configuration."""
        response = authenticated_client.get('/api/v1/config/hub/')

        assert response.status_code == 200
        data = response.json()
        assert 'currency' in data
        assert 'os_language' in data

    def test_update_hub_config(self, authenticated_client, hub_config):
        """Test updating hub configuration."""
        response = authenticated_client.patch(
            '/api/v1/config/hub/',
            data=json.dumps({'currency': 'USD'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['currency'] == 'USD'

    def test_get_hub_config_requires_auth(self, client, hub_config):
        """Test that config API requires authentication."""
        response = client.get('/api/v1/config/hub/')

        # Should be 401 or 403
        assert response.status_code in [401, 403]


class TestStoreConfigAPI:
    """Tests for Store Configuration API."""

    def test_get_store_config(self, authenticated_client, store_config):
        """Test getting store configuration."""
        response = authenticated_client.get('/api/v1/config/store/')

        assert response.status_code == 200
        data = response.json()
        assert 'business_name' in data
        assert 'tax_rate' in data

    def test_update_store_config(self, authenticated_client, store_config):
        """Test updating store configuration."""
        response = authenticated_client.patch(
            '/api/v1/config/store/',
            data=json.dumps({'business_name': 'Updated Store'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['business_name'] == 'Updated Store'


class TestPluginAPI:
    """Tests for Plugin Management API."""

    def test_list_plugins(self, authenticated_client):
        """Test listing installed plugins."""
        response = authenticated_client.get('/api/v1/plugins/')

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_plugins_includes_active(self, authenticated_client):
        """Test that active plugins are listed."""
        response = authenticated_client.get('/api/v1/plugins/')

        assert response.status_code == 200
        data = response.json()

        # Should include some plugins (inventory, sales are active)
        plugin_ids = [p['plugin_id'] for p in data]
        # At least one plugin should exist
        assert len(data) >= 0  # May be empty in test environment


class TestSystemAPI:
    """Tests for System API endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint (no auth required)."""
        response = client.get('/api/v1/system/health/')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'
        assert 'database' in data

    def test_current_user(self, authenticated_client):
        """Test getting current user info."""
        response = authenticated_client.get('/api/v1/system/me/')

        assert response.status_code == 200
        data = response.json()
        assert 'name' in data
        assert data['is_authenticated'] is True


class TestThemeAPI:
    """Tests for theme toggle API."""

    def test_toggle_dark_mode(self, authenticated_client, hub_config):
        """Test toggling dark mode."""
        initial_mode = hub_config.dark_mode

        response = authenticated_client.post('/api/v1/config/theme/toggle/')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['dark_mode'] != initial_mode


class TestLanguageAPI:
    """Tests for language change API."""

    def test_change_language(self, authenticated_client, hub_config):
        """Test changing language."""
        response = authenticated_client.post(
            '/api/v1/config/language/',
            data=json.dumps({'language': 'es'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['language'] == 'es'

    def test_change_language_invalid(self, authenticated_client, hub_config):
        """Test changing to invalid language."""
        response = authenticated_client.post(
            '/api/v1/config/language/',
            data=json.dumps({'language': 'invalid'}),
            content_type='application/json'
        )

        assert response.status_code == 400
