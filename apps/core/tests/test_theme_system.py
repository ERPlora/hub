"""
Tests for theme system (color themes and dark mode).

Theme preferences are stored in HubConfig model and applied client-side via JS.
"""
import pytest
from django.test import Client
from django.urls import reverse
from apps.configuration.models import HubConfig, StoreConfig
from apps.accounts.models import LocalUser


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def hub_config(db):
    """Create HubConfig instance with is_configured=True to skip setup wizard."""
    config = HubConfig.get_config()
    config.is_configured = True
    config.save()
    # Also configure StoreConfig to skip the setup wizard middleware
    store_config = StoreConfig.get_config()
    store_config.is_configured = True
    store_config.save()
    return config


@pytest.fixture
def local_user(db):
    """Create a local user for testing."""
    user = LocalUser.objects.create(
        cloud_user_id=1,
        email='test@example.com',
        name='Test User',
        role='admin',
        is_active=True
    )
    user.set_pin('1234')
    return user


@pytest.fixture
def authenticated_client(client, local_user):
    """Client with authenticated session."""
    session = client.session
    session['local_user_id'] = str(local_user.id)
    session['user_name'] = local_user.name
    session['user_email'] = local_user.email
    session['user_role'] = local_user.role
    session.save()
    return client


@pytest.mark.django_db
class TestHubConfigModel:
    """Test HubConfig model for theme preferences."""

    def test_default_theme_values(self, hub_config):
        """Test default theme values."""
        assert hub_config.color_theme == 'default'
        assert hub_config.dark_mode is False
        assert hub_config.auto_print is False

    def test_color_theme_choices(self, hub_config):
        """Test color theme can be set to valid choices."""
        hub_config.color_theme = 'blue'
        hub_config.save()
        hub_config.refresh_from_db()
        assert hub_config.color_theme == 'blue'

    def test_dark_mode_toggle(self, hub_config):
        """Test dark mode can be toggled."""
        assert hub_config.dark_mode is False
        hub_config.dark_mode = True
        hub_config.save()
        hub_config.refresh_from_db()
        assert hub_config.dark_mode is True

    def test_auto_print_toggle(self, hub_config):
        """Test auto-print can be toggled."""
        assert hub_config.auto_print is False
        hub_config.auto_print = True
        hub_config.save()
        hub_config.refresh_from_db()
        assert hub_config.auto_print is True


@pytest.mark.django_db
class TestThemeContextProcessor:
    """Test that hub_config is available in template context."""

    def test_hub_config_in_context(self, authenticated_client, hub_config):
        """Test hub_config is available in settings view."""
        response = authenticated_client.get(reverse('main:settings'))
        assert response.status_code == 200
        assert 'hub_config' in response.context
        assert response.context['hub_config'] == hub_config

    def test_hub_config_in_dashboard(self, authenticated_client, hub_config):
        """Test hub_config is available in dashboard view."""
        response = authenticated_client.get(reverse('main:index'))
        assert response.status_code == 200
        assert 'hub_config' in response.context
