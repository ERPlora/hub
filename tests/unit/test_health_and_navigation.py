"""
Unit tests for health check and core navigation.

Tests health endpoint, dashboard, settings, employees, and auth redirects.
URL patterns:
- health_check -> /health/
- main:index -> / (dashboard / home)
- main:settings -> /settings/
- main:employees -> /employees/
- auth:login -> /login/
"""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse


pytestmark = pytest.mark.unit


class TestHealthCheck:
    """Tests for the health check endpoint.

    Note: /health/ is behind JWT middleware in the Hub (only /ht/ is exempt).
    These tests use an authenticated client.
    """

    def test_health_check_returns_200(self, authenticated_client):
        """Health check should return 200 for authenticated users."""
        url = reverse('health_check')
        response = authenticated_client.get(url)

        assert response.status_code == 200

    def test_health_check_returns_json(self, authenticated_client):
        """Health check should return JSON with status ok."""
        url = reverse('health_check')
        response = authenticated_client.get(url)

        assert response['Content-Type'] == 'application/json'
        data = response.json()
        assert data['status'] == 'ok'

    def test_health_check_includes_database_status(self, authenticated_client):
        """Health check should verify database connectivity."""
        url = reverse('health_check')
        response = authenticated_client.get(url)

        data = response.json()
        assert data['database'] == 'ok'

    def test_health_check_includes_version(self, authenticated_client):
        """Health check should include Hub version."""
        url = reverse('health_check')
        response = authenticated_client.get(url)

        data = response.json()
        assert 'version' in data

    def test_health_check_url_resolves(self):
        """Health check URL should resolve to /health/."""
        url = reverse('health_check')
        assert url == '/health/'


class TestDashboard:
    """Tests for the dashboard/home page."""

    @patch('apps.modules_runtime.loader.module_loader')
    def test_dashboard_loads_for_authenticated_user(self, mock_loader, authenticated_client):
        """Dashboard should load with 200 for authenticated users."""
        mock_loader.get_menu_items.return_value = []

        url = reverse('main:index')
        response = authenticated_client.get(url)

        assert response.status_code == 200

    @patch('apps.modules_runtime.loader.module_loader')
    def test_dashboard_contains_home_section(self, mock_loader, authenticated_client):
        """Dashboard should load with module menu items."""
        mock_loader.get_menu_items.return_value = [
            {
                'module_id': 'inventory',
                'label': 'Inventory',
                'icon': 'cube-outline',
                'url': '/m/inventory/',
            },
        ]

        url = reverse('main:index')
        response = authenticated_client.get(url)

        assert response.status_code == 200


class TestSettingsPage:
    """Tests for the settings page."""

    @patch('apps.configuration.scheduler.get_scheduler_status')
    def test_settings_page_loads(self, mock_scheduler, authenticated_client):
        """Settings page should load with 200 for authenticated users."""
        mock_scheduler.return_value = {'running': False, 'next_run': None}

        url = reverse('main:settings')
        response = authenticated_client.get(url)

        assert response.status_code == 200


class TestEmployeesPage:
    """Tests for the employees page."""

    def test_employees_page_loads(self, authenticated_client, hub_config):
        """Employees page should load with 200 for authenticated users."""
        url = reverse('main:employees')
        response = authenticated_client.get(url)

        assert response.status_code == 200


class TestLoginPage:
    """Tests for the login page accessibility."""

    def test_login_page_loads_for_unauthenticated_users(self, client, db, store_config):
        """Login page should load with 200 for unauthenticated users."""
        url = reverse('auth:login')
        response = client.get(url)

        assert response.status_code == 200


class TestAuthRedirects:
    """Tests for authentication redirects on protected pages."""

    def test_unauthenticated_redirected_from_dashboard(self, client, db, store_config):
        """Unauthenticated users should be redirected from the dashboard."""
        url = reverse('main:index')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url

    def test_unauthenticated_redirected_from_settings(self, client, db, store_config):
        """Unauthenticated users should be redirected from the settings page."""
        url = reverse('main:settings')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url

    def test_unauthenticated_redirected_from_employees(self, client, db, store_config):
        """Unauthenticated users should be redirected from the employees page."""
        url = reverse('main:employees')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url

    def test_unauthenticated_redirected_from_setup(self, client, db, store_config):
        """Unauthenticated users should be redirected from the setup wizard."""
        url = reverse('setup:wizard')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url
