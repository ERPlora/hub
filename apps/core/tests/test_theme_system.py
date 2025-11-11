"""
Tests for theme system (color themes and dark mode).
"""
import pytest
from django.test import Client
from django.urls import reverse
from apps.core.models import HubConfig, LocalUser


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def hub_config(db):
    """Create HubConfig instance."""
    return HubConfig.get_config()


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
    session['local_user_id'] = local_user.id
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
        response = authenticated_client.get(reverse('configuration:settings'))
        assert response.status_code == 200
        assert 'hub_config' in response.context
        assert response.context['hub_config'] == hub_config

    def test_hub_config_in_dashboard(self, authenticated_client, hub_config):
        """Test hub_config is available in dashboard view."""
        response = authenticated_client.get(reverse('configuration:dashboard'))
        assert response.status_code == 200
        assert 'hub_config' in response.context


@pytest.mark.django_db
class TestThemeAPI:
    """Test theme update API endpoint."""

    def test_update_color_theme(self, authenticated_client, hub_config):
        """Test updating color theme via POST."""
        assert hub_config.color_theme == 'default'

        response = authenticated_client.post(
            reverse('configuration:settings'),
            data={
                'action': 'update_theme',
                'color_theme': 'blue',
                'dark_mode': 'false',
                'auto_print': 'false'
            }
        )

        assert response.status_code == 200
        hub_config.refresh_from_db()
        assert hub_config.color_theme == 'blue'

    def test_update_dark_mode(self, authenticated_client, hub_config):
        """Test enabling dark mode via POST."""
        assert hub_config.dark_mode is False

        response = authenticated_client.post(
            reverse('configuration:settings'),
            data={
                'action': 'update_theme',
                'color_theme': 'default',
                'dark_mode': 'true',
                'auto_print': 'false'
            }
        )

        assert response.status_code == 200
        hub_config.refresh_from_db()
        assert hub_config.dark_mode is True

    def test_update_auto_print(self, authenticated_client, hub_config):
        """Test enabling auto-print via POST."""
        assert hub_config.auto_print is False

        response = authenticated_client.post(
            reverse('configuration:settings'),
            data={
                'action': 'update_theme',
                'color_theme': 'default',
                'dark_mode': 'false',
                'auto_print': 'true'
            }
        )

        assert response.status_code == 200
        hub_config.refresh_from_db()
        assert hub_config.auto_print is True

    def test_update_all_preferences(self, authenticated_client, hub_config):
        """Test updating all theme preferences at once."""
        response = authenticated_client.post(
            reverse('configuration:settings'),
            data={
                'action': 'update_theme',
                'color_theme': 'blue',
                'dark_mode': 'true',
                'auto_print': 'true'
            }
        )

        assert response.status_code == 200
        hub_config.refresh_from_db()
        assert hub_config.color_theme == 'blue'
        assert hub_config.dark_mode is True
        assert hub_config.auto_print is True

    def test_theme_update_requires_authentication(self, client):
        """Test that theme update requires authentication."""
        response = client.post(
            reverse('configuration:settings'),
            data={
                'action': 'update_theme',
                'color_theme': 'blue',
                'dark_mode': 'true',
                'auto_print': 'false'
            }
        )

        # Should redirect to login
        assert response.status_code == 302
        assert response.url == reverse('accounts:login')


@pytest.mark.django_db
class TestThemeTemplateRendering:
    """Test that theme is correctly rendered in templates."""

    def test_default_theme_rendered(self, authenticated_client, hub_config):
        """Test that default theme is loaded in template."""
        response = authenticated_client.get(reverse('configuration:dashboard'))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'ionic-theme-default.css' in content

    def test_blue_theme_rendered(self, authenticated_client, hub_config):
        """Test that blue theme is loaded when selected."""
        hub_config.color_theme = 'blue'
        hub_config.save()

        response = authenticated_client.get(reverse('configuration:dashboard'))
        assert response.status_code == 200
        content = response.content.decode()
        assert 'ionic-theme-blue.css' in content

    def test_dark_mode_class_applied(self, authenticated_client, hub_config):
        """Test that dark class is applied when dark mode is enabled."""
        hub_config.dark_mode = True
        hub_config.save()

        response = authenticated_client.get(reverse('configuration:dashboard'))
        assert response.status_code == 200
        content = response.content.decode()
        # Check that dark mode is applied in script
        assert "document.body.classList.add('dark')" in content


@pytest.mark.django_db
class TestThemePersistence:
    """Test that theme preferences persist across sessions."""

    def test_theme_persists_after_logout(self, authenticated_client, hub_config):
        """Test that theme preferences persist after logout."""
        # Set theme preferences
        authenticated_client.post(
            reverse('configuration:settings'),
            data={
                'action': 'update_theme',
                'color_theme': 'blue',
                'dark_mode': 'true',
                'auto_print': 'true'
            }
        )

        # Logout
        authenticated_client.get(reverse('accounts:logout'))

        # Check that preferences are still in database
        hub_config.refresh_from_db()
        assert hub_config.color_theme == 'blue'
        assert hub_config.dark_mode is True
        assert hub_config.auto_print is True
