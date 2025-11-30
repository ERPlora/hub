"""
Pytest fixtures shared across all Hub tests.
"""
import pytest
from unittest.mock import patch, MagicMock


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
