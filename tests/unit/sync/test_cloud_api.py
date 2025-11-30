"""
Unit tests for CloudAPIService.

Tests the Hub's Cloud API client service.
"""
import pytest
import responses
from unittest.mock import patch, MagicMock, PropertyMock
from requests.exceptions import Timeout, ConnectionError


# Mark all tests in this module
pytestmark = pytest.mark.unit


@pytest.fixture
def mock_hub_config():
    """Mock HubConfig with JWT credentials."""
    with patch('apps.sync.services.cloud_api.HubConfig') as mock:
        config = MagicMock()
        config.hub_jwt = 'test.jwt.token'
        config.hub_id = 'test-hub-id'
        config.cloud_public_key = ''
        mock.get_solo.return_value = config
        mock.set_value = MagicMock()
        yield mock


@pytest.fixture
def cloud_api(mock_hub_config):
    """Create CloudAPIService with mocked config."""
    with patch('apps.sync.services.cloud_api.settings') as mock_settings:
        mock_settings.CLOUD_API_URL = 'https://api.test.com'
        mock_settings.HUB_VERSION = '1.0.0'

        from apps.sync.services.cloud_api import CloudAPIService
        return CloudAPIService()


class TestCloudAPIServiceInit:
    """Tests for CloudAPIService initialization."""

    def test_init_with_config(self, mock_hub_config):
        """Test initialization reads config correctly."""
        with patch('apps.sync.services.cloud_api.settings') as mock_settings:
            mock_settings.CLOUD_API_URL = 'https://cloud.example.com'

            from apps.sync.services.cloud_api import CloudAPIService
            service = CloudAPIService()

            assert service.hub_jwt == 'test.jwt.token'
            assert service.hub_id == 'test-hub-id'
            assert service.base_url == 'https://cloud.example.com'

    def test_is_configured_with_jwt(self, cloud_api):
        """Test is_configured returns True when JWT is set."""
        assert cloud_api.is_configured is True

    def test_is_configured_without_jwt(self, mock_hub_config):
        """Test is_configured returns False when JWT is missing."""
        mock_hub_config.get_solo.return_value.hub_jwt = ''

        with patch('apps.sync.services.cloud_api.settings'):
            from apps.sync.services.cloud_api import CloudAPIService
            service = CloudAPIService()

            assert service.is_configured is False


class TestCloudAPIServiceHeaders:
    """Tests for request headers."""

    def test_get_headers_with_jwt(self, cloud_api):
        """Test headers include JWT authorization."""
        headers = cloud_api._get_headers()

        assert headers['Content-Type'] == 'application/json'
        assert headers['Accept'] == 'application/json'
        assert headers['Authorization'] == 'Bearer test.jwt.token'

    def test_get_headers_without_jwt(self, mock_hub_config):
        """Test headers without JWT authorization."""
        mock_hub_config.get_solo.return_value.hub_jwt = ''

        with patch('apps.sync.services.cloud_api.settings'):
            from apps.sync.services.cloud_api import CloudAPIService
            service = CloudAPIService()
            headers = service._get_headers()

            assert 'Authorization' not in headers


class TestCloudAPIServiceRequest:
    """Tests for the _request method."""

    @responses.activate
    def test_request_success(self, cloud_api):
        """Test successful API request."""
        responses.add(
            responses.POST,
            'https://api.test.com/api/test/',
            json={'result': 'success'},
            status=200
        )

        result = cloud_api._request('POST', '/api/test/', data={'foo': 'bar'})

        assert result == {'result': 'success'}
        assert len(responses.calls) == 1
        assert responses.calls[0].request.headers['Authorization'] == 'Bearer test.jwt.token'

    @responses.activate
    def test_request_not_configured(self, mock_hub_config):
        """Test request fails when not configured."""
        mock_hub_config.get_solo.return_value.hub_jwt = ''

        with patch('apps.sync.services.cloud_api.settings'):
            from apps.sync.services.cloud_api import CloudAPIService, CloudAPIError
            service = CloudAPIService()

            with pytest.raises(CloudAPIError, match="not configured"):
                service._request('GET', '/api/test/')

    @responses.activate
    def test_request_unauthorized(self, cloud_api):
        """Test handling 401 unauthorized response."""
        from apps.sync.services.cloud_api import CloudAPIError

        responses.add(
            responses.GET,
            'https://api.test.com/api/test/',
            status=401
        )

        with pytest.raises(CloudAPIError) as exc_info:
            cloud_api._request('GET', '/api/test/')

        assert exc_info.value.status_code == 401
        assert "Unauthorized" in exc_info.value.message

    @responses.activate
    def test_request_forbidden(self, cloud_api):
        """Test handling 403 forbidden response."""
        from apps.sync.services.cloud_api import CloudAPIError

        responses.add(
            responses.GET,
            'https://api.test.com/api/test/',
            status=403
        )

        with pytest.raises(CloudAPIError) as exc_info:
            cloud_api._request('GET', '/api/test/')

        assert exc_info.value.status_code == 403

    @responses.activate
    def test_request_server_error(self, cloud_api):
        """Test handling 500 server error."""
        from apps.sync.services.cloud_api import CloudAPIError

        responses.add(
            responses.GET,
            'https://api.test.com/api/test/',
            json={'error': 'Internal server error'},
            status=500
        )

        with pytest.raises(CloudAPIError) as exc_info:
            cloud_api._request('GET', '/api/test/')

        assert exc_info.value.status_code == 500

    @responses.activate
    def test_request_timeout(self, cloud_api):
        """Test handling request timeout."""
        from apps.sync.services.cloud_api import CloudAPIError

        responses.add(
            responses.GET,
            'https://api.test.com/api/test/',
            body=Timeout()
        )

        with pytest.raises(CloudAPIError, match="timeout"):
            cloud_api._request('GET', '/api/test/')

    @responses.activate
    def test_request_connection_error(self, cloud_api):
        """Test handling connection error."""
        from apps.sync.services.cloud_api import CloudAPIError

        responses.add(
            responses.GET,
            'https://api.test.com/api/test/',
            body=ConnectionError()
        )

        with pytest.raises(CloudAPIError, match="Connection error"):
            cloud_api._request('GET', '/api/test/')


class TestHeartbeatMethods:
    """Tests for heartbeat-related methods."""

    @responses.activate
    def test_send_heartbeat_success(self, cloud_api):
        """Test sending heartbeat successfully."""
        responses.add(
            responses.POST,
            'https://api.test.com/api/hubs/me/heartbeat/',
            json={'success': True, 'timestamp': '2025-01-01T00:00:00Z'},
            status=200
        )

        result = cloud_api.send_heartbeat()

        assert result['success'] is True
        assert 'timestamp' in result

    @responses.activate
    def test_send_heartbeat_with_metadata(self, cloud_api):
        """Test sending heartbeat with custom metadata."""
        responses.add(
            responses.POST,
            'https://api.test.com/api/hubs/me/heartbeat/',
            json={'success': True},
            status=200
        )

        metadata = {
            'version': '2.0.0',
            'plugins': ['inventory'],
            'status': 'healthy'
        }
        cloud_api.send_heartbeat(metadata)

        # Verify request body
        import json
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body['version'] == '2.0.0'
        assert request_body['plugins'] == ['inventory']

    @responses.activate
    def test_get_hub_info(self, cloud_api):
        """Test getting hub info."""
        responses.add(
            responses.GET,
            'https://api.test.com/api/hubs/me/',
            json={
                'hub_id': 'test-id',
                'slug': 'test-hub',
                'name': 'Test Hub'
            },
            status=200
        )

        result = cloud_api.get_hub_info()

        assert result['hub_id'] == 'test-id'
        assert result['slug'] == 'test-hub'


class TestCommandMethods:
    """Tests for command-related methods."""

    @responses.activate
    def test_get_pending_commands_empty(self, cloud_api):
        """Test getting pending commands when none exist."""
        responses.add(
            responses.GET,
            'https://api.test.com/api/hubs/me/commands/',
            json={'commands': []},
            status=200
        )

        result = cloud_api.get_pending_commands()

        assert result == []

    @responses.activate
    def test_get_pending_commands_with_data(self, cloud_api):
        """Test getting pending commands."""
        responses.add(
            responses.GET,
            'https://api.test.com/api/hubs/me/commands/',
            json={
                'commands': [
                    {
                        'id': 'cmd-1',
                        'type': 'install_plugin',
                        'payload': {'plugin_id': 'inventory'}
                    },
                    {
                        'id': 'cmd-2',
                        'type': 'sync_config',
                        'payload': {}
                    }
                ]
            },
            status=200
        )

        result = cloud_api.get_pending_commands()

        assert len(result) == 2
        assert result[0]['id'] == 'cmd-1'
        assert result[1]['type'] == 'sync_config'

    @responses.activate
    def test_acknowledge_command_completed(self, cloud_api):
        """Test acknowledging command as completed."""
        responses.add(
            responses.POST,
            'https://api.test.com/api/hubs/me/commands/cmd-123/ack/',
            json={'success': True, 'command_id': 'cmd-123'},
            status=200
        )

        result = cloud_api.acknowledge_command(
            command_id='cmd-123',
            status='completed',
            result={'installed': True}
        )

        assert result['success'] is True

        # Verify request body
        import json
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body['status'] == 'completed'
        assert request_body['result'] == {'installed': True}

    @responses.activate
    def test_acknowledge_command_failed(self, cloud_api):
        """Test acknowledging command as failed."""
        responses.add(
            responses.POST,
            'https://api.test.com/api/hubs/me/commands/cmd-456/ack/',
            json={'success': True},
            status=200
        )

        cloud_api.acknowledge_command(
            command_id='cmd-456',
            status='failed',
            error='Plugin not found'
        )

        import json
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body['status'] == 'failed'
        assert request_body['error'] == 'Plugin not found'


class TestJWTVerification:
    """Tests for command JWT verification."""

    def test_verify_command_jwt_valid(self, cloud_api, mock_hub_config):
        """Test verifying a valid command JWT."""
        # Mock public key
        mock_hub_config.get_solo.return_value.cloud_public_key = 'test-public-key'

        with patch('apps.sync.services.cloud_api.jwt.decode') as mock_decode:
            mock_decode.return_value = {
                'type': 'hub_command',
                'hub_id': 'test-hub-id',
                'command': 'install_plugin'
            }

            result = cloud_api.verify_command_jwt('valid.jwt.token')

            assert result is not None
            assert result['type'] == 'hub_command'
            assert result['command'] == 'install_plugin'

    def test_verify_command_jwt_wrong_type(self, cloud_api, mock_hub_config):
        """Test verifying JWT with wrong type returns None."""
        mock_hub_config.get_solo.return_value.cloud_public_key = 'test-public-key'

        with patch('apps.sync.services.cloud_api.jwt.decode') as mock_decode:
            mock_decode.return_value = {
                'type': 'hub_auth',  # Wrong type
                'hub_id': 'test-hub-id'
            }

            result = cloud_api.verify_command_jwt('wrong.type.token')

            assert result is None

    def test_verify_command_jwt_wrong_hub(self, cloud_api, mock_hub_config):
        """Test verifying JWT for different hub returns None."""
        mock_hub_config.get_solo.return_value.cloud_public_key = 'test-public-key'

        with patch('apps.sync.services.cloud_api.jwt.decode') as mock_decode:
            mock_decode.return_value = {
                'type': 'hub_command',
                'hub_id': 'different-hub-id'  # Wrong hub
            }

            result = cloud_api.verify_command_jwt('wrong.hub.token')

            assert result is None

    def test_verify_command_jwt_expired(self, cloud_api, mock_hub_config):
        """Test verifying expired JWT returns None."""
        import jwt as pyjwt
        mock_hub_config.get_solo.return_value.cloud_public_key = 'test-public-key'

        with patch('apps.sync.services.cloud_api.jwt.decode') as mock_decode:
            mock_decode.side_effect = pyjwt.ExpiredSignatureError()

            result = cloud_api.verify_command_jwt('expired.jwt.token')

            assert result is None

    @responses.activate
    def test_get_public_key_from_cloud(self, cloud_api, mock_hub_config):
        """Test fetching public key from Cloud when not cached."""
        mock_hub_config.get_solo.return_value.cloud_public_key = ''

        responses.add(
            responses.GET,
            'https://api.test.com/api/auth/public-key/',
            json={'public_key': '-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----'},
            status=200
        )

        result = cloud_api._get_public_key()

        assert result == '-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----'
        # Verify key was cached
        mock_hub_config.set_value.assert_called_once()


class TestSingletonAndHelpers:
    """Tests for singleton and helper functions."""

    def test_get_cloud_api_returns_singleton(self, mock_hub_config):
        """Test get_cloud_api returns same instance."""
        with patch('apps.sync.services.cloud_api.settings'):
            # Reset singleton
            import apps.sync.services.cloud_api as module
            module._cloud_api_instance = None

            from apps.sync.services.cloud_api import get_cloud_api

            instance1 = get_cloud_api()
            instance2 = get_cloud_api()

            assert instance1 is instance2

            # Cleanup
            module._cloud_api_instance = None
