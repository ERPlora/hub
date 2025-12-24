"""
Pytest fixtures shared across all Hub tests.
"""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import Client


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def authenticated_client(db, client):
    """Client with authenticated session."""
    from apps.accounts.models import LocalUser

    # Create test user
    user = LocalUser.objects.create(
        name='Test User',
        email='test@example.com',
        role='admin',
        pin_hash='',
        is_active=True
    )
    user.set_pin('1234')

    # Simulate login by setting session
    session = client.session
    session['local_user_id'] = str(user.id)  # Convert UUID to string for session
    session['user_name'] = user.name
    session['user_email'] = user.email
    session['user_role'] = user.role
    session.save()

    return client


@pytest.fixture
def hub_config(db):
    """HubConfig instance for testing."""
    from apps.configuration.models import HubConfig

    config = HubConfig.get_solo()
    config.currency = 'EUR'
    config.os_language = 'en'
    config.save()
    return config


@pytest.fixture
def store_config(db):
    """StoreConfig instance for testing."""
    from apps.configuration.models import StoreConfig

    config = StoreConfig.get_solo()
    config.business_name = 'Test Store'
    config.business_address = '123 Test Street'
    config.vat_number = 'ES12345678A'
    config.tax_rate = Decimal('21.00')
    config.tax_included = True
    config.is_configured = True
    config.save()
    return config


@pytest.fixture
def unconfigured_store(db):
    """Unconfigured StoreConfig for wizard tests."""
    from apps.configuration.models import StoreConfig

    config = StoreConfig.get_solo()
    config.business_name = ''
    config.business_address = ''
    config.vat_number = ''
    config.is_configured = False
    config.save()
    return config


# =============================================================================
# Mock Fixtures (for tests that don't need database)
# =============================================================================

@pytest.fixture
def mock_hub_config():
    """
    Mock HubConfig for tests that don't need database access.
    """
    with patch('apps.configuration.models.HubConfig') as mock_class:
        config = MagicMock()
        config.hub_id = 'test-hub-id-123'
        config.hub_jwt = 'test.jwt.token'
        config.cloud_public_key = ''
        config.cloud_api_token = ''
        config.is_configured = True
        config.currency = 'EUR'
        config.os_language = 'en'
        config.dark_mode = False

        mock_class.get_solo.return_value = config
        mock_class.get_value = MagicMock(side_effect=lambda k, d=None: getattr(config, k, d))
        mock_class.set_value = MagicMock()

        yield mock_class


@pytest.fixture
def mock_store_config():
    """
    Mock StoreConfig for tests that don't need database access.
    """
    with patch('apps.configuration.models.StoreConfig') as mock_class:
        config = MagicMock()
        config.business_name = 'Test Store'
        config.business_address = '123 Test St'
        config.vat_number = 'ES12345678A'
        config.tax_rate = 21.00
        config.tax_included = True
        config.is_configured = True

        mock_class.get_solo.return_value = config
        mock_class.get_value = MagicMock(side_effect=lambda k, d=None: getattr(config, k, d))
        mock_class.set_value = MagicMock()

        yield mock_class


@pytest.fixture
def mock_settings():
    """
    Mock Django settings for tests.
    """
    with patch('django.conf.settings') as mock:
        mock.CLOUD_API_URL = 'https://test.erplora.com'
        mock.HUB_VERSION = '1.0.0'
        mock.HEARTBEAT_ENABLED = True
        mock.HEARTBEAT_INTERVAL = 60
        mock.COMMAND_POLL_INTERVAL = 300
        mock.DEPLOYMENT_MODE = 'local'
        mock.DEBUG = True
        yield mock
