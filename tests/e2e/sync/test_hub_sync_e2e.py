"""
End-to-end tests for Hub synchronization with Cloud.

Tests the complete flow of Hub-Cloud communication simulating
real-world scenarios.
"""
import pytest
import responses
import json
from unittest.mock import patch, MagicMock
from freezegun import freeze_time


# Mark all tests in this module
pytestmark = pytest.mark.e2e


@pytest.fixture
def hub_config():
    """Setup HubConfig with test data."""
    with patch('apps.configuration.models.HubConfig') as mock_class:
        config = MagicMock()
        config.hub_id = 'e2e-test-hub-id'
        config.hub_jwt = 'e2e.test.jwt.token'
        config.cloud_public_key = ''
        config.is_configured = True
        mock_class.get_solo.return_value = config
        mock_class.set_value = MagicMock()
        mock_class.get_value = MagicMock(return_value='EUR')
        yield mock_class


@pytest.fixture
def mock_settings():
    """Mock Django settings for e2e tests."""
    with patch('apps.sync.services.cloud_api.settings') as mock:
        mock.CLOUD_API_URL = 'https://cloud.erplora.com'
        mock.HUB_VERSION = '1.0.0'
        yield mock


class TestHubStartupSync:
    """E2E tests for Hub startup synchronization."""

    @responses.activate
    def test_hub_startup_sends_heartbeat(self, hub_config, mock_settings):
        """Test that Hub sends heartbeat on startup."""
        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/heartbeat/',
            json={'success': True, 'timestamp': '2025-01-01T00:00:00Z'},
            status=200
        )

        from apps.sync.services.cloud_api import CloudAPIService

        service = CloudAPIService()
        result = service.send_heartbeat({
            'version': '1.0.0',
            'status': 'starting'
        })

        assert result['success'] is True
        assert len(responses.calls) == 1

        # Verify request
        request = responses.calls[0].request
        assert 'Bearer e2e.test.jwt.token' in request.headers['Authorization']

    @responses.activate
    def test_hub_fetches_pending_commands_on_startup(self, hub_config, mock_settings):
        """Test Hub fetches pending commands on startup."""
        responses.add(
            responses.GET,
            'https://cloud.erplora.com/api/hubs/me/commands/',
            json={
                'commands': [
                    {
                        'id': 'startup-cmd-1',
                        'type': 'sync_config',
                        'payload': {'force': True},
                        'command_jwt': 'cmd.jwt.token'
                    }
                ]
            },
            status=200
        )

        from apps.sync.services.cloud_api import CloudAPIService

        service = CloudAPIService()
        commands = service.get_pending_commands()

        assert len(commands) == 1
        assert commands[0]['id'] == 'startup-cmd-1'
        assert commands[0]['type'] == 'sync_config'


class TestModuleInstallationFlow:
    """E2E tests for module installation via Cloud commands."""

    @responses.activate
    def test_install_module_flow(self, hub_config, mock_settings):
        """Test complete module installation flow."""
        # 1. Hub polls commands
        responses.add(
            responses.GET,
            'https://cloud.erplora.com/api/hubs/me/commands/',
            json={
                'commands': [
                    {
                        'id': 'install-1',
                        'type': 'install_module',
                        'payload': {
                            'module_id': 'inventory',
                            'version': '1.0.0',
                            'download_url': 'https://cloud.erplora.com/modules/inventory/1.0.0.zip'
                        },
                        'command_jwt': 'install.cmd.jwt'
                    }
                ]
            },
            status=200
        )

        # 2. Hub acknowledges installation
        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/commands/install-1/ack/',
            json={'success': True, 'command_id': 'install-1'},
            status=200
        )

        from apps.sync.services.cloud_api import CloudAPIService

        service = CloudAPIService()

        # Poll commands
        commands = service.get_pending_commands()
        assert len(commands) == 1
        assert commands[0]['type'] == 'install_module'

        # Simulate installation and ack
        result = service.acknowledge_command(
            command_id='install-1',
            status='completed',
            result={'installed': True, 'module_id': 'inventory', 'version': '1.0.0'}
        )

        assert result['success'] is True

    @responses.activate
    def test_module_installation_failure_flow(self, hub_config, mock_settings):
        """Test module installation failure handling."""
        responses.add(
            responses.GET,
            'https://cloud.erplora.com/api/hubs/me/commands/',
            json={
                'commands': [
                    {
                        'id': 'install-fail-1',
                        'type': 'install_module',
                        'payload': {'module_id': 'nonexistent'},
                        'command_jwt': 'fail.cmd.jwt'
                    }
                ]
            },
            status=200
        )

        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/commands/install-fail-1/ack/',
            json={'success': True},
            status=200
        )

        from apps.sync.services.cloud_api import CloudAPIService

        service = CloudAPIService()
        commands = service.get_pending_commands()

        # Ack as failed
        service.acknowledge_command(
            command_id='install-fail-1',
            status='failed',
            error='Module not found in marketplace'
        )

        # Verify error was sent
        ack_request = responses.calls[1].request
        body = json.loads(ack_request.body)
        assert body['status'] == 'failed'
        assert 'not found' in body['error']


class TestHeartbeatResilience:
    """E2E tests for heartbeat resilience."""

    @responses.activate
    def test_heartbeat_retry_on_network_failure(self, hub_config, mock_settings):
        """Test heartbeat handles network failures gracefully."""
        from apps.sync.services.cloud_api import CloudAPIService, CloudAPIError
        from requests.exceptions import ConnectionError

        # First call fails
        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/heartbeat/',
            body=ConnectionError()
        )

        service = CloudAPIService()

        # Should not crash
        with pytest.raises(CloudAPIError):
            service.send_heartbeat()

        # Add success response for retry
        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/heartbeat/',
            json={'success': True},
            status=200
        )

        # Second call succeeds
        result = service.send_heartbeat()
        assert result['success'] is True

    @responses.activate
    def test_heartbeat_handles_server_overload(self, hub_config, mock_settings):
        """Test heartbeat handles 503 server overload."""
        from apps.sync.services.cloud_api import CloudAPIService, CloudAPIError

        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/heartbeat/',
            json={'error': 'Service temporarily unavailable'},
            status=503
        )

        service = CloudAPIService()

        with pytest.raises(CloudAPIError) as exc_info:
            service.send_heartbeat()

        assert exc_info.value.status_code == 503


class TestOfflineMode:
    """E2E tests for offline mode handling."""

    @responses.activate
    def test_hub_continues_without_cloud(self, hub_config, mock_settings):
        """Test Hub continues operation when Cloud is unreachable."""
        from apps.sync.services.cloud_api import CloudAPIError
        from requests.exceptions import ConnectionError

        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/heartbeat/',
            body=ConnectionError()
        )

        from apps.sync.services.heartbeat import HeartbeatService
        from apps.sync.services.cloud_api import CloudAPIService

        service = CloudAPIService()
        heartbeat = HeartbeatService(
            heartbeat_interval=1,
            command_poll_interval=1,
            cloud_api=service
        )

        # Heartbeat loop should handle errors gracefully
        heartbeat._send_heartbeat()  # Should not raise

    def test_offline_mode_with_no_jwt(self, mock_settings):
        """Test Hub works without JWT (offline mode)."""
        with patch('apps.configuration.models.HubConfig') as mock_config:
            config = MagicMock()
            config.hub_id = 'offline-hub'
            config.hub_jwt = ''  # No JWT
            mock_config.get_solo.return_value = config

            from apps.sync.services.cloud_api import CloudAPIService

            service = CloudAPIService()

            assert service.is_configured is False

            # Service should not be started when not configured
            from apps.sync.services.heartbeat import HeartbeatService

            heartbeat = HeartbeatService(cloud_api=service)
            heartbeat.start()

            assert heartbeat._running is False


class TestMultipleCommandsFlow:
    """E2E tests for handling multiple commands."""

    @responses.activate
    def test_execute_multiple_commands_in_order(self, hub_config, mock_settings):
        """Test multiple commands are executed in correct order."""
        responses.add(
            responses.GET,
            'https://cloud.erplora.com/api/hubs/me/commands/',
            json={
                'commands': [
                    {
                        'id': 'cmd-1',
                        'type': 'sync_config',
                        'payload': {},
                        'command_jwt': 'jwt1'
                    },
                    {
                        'id': 'cmd-2',
                        'type': 'install_module',
                        'payload': {'module_id': 'sales'},
                        'command_jwt': 'jwt2'
                    },
                    {
                        'id': 'cmd-3',
                        'type': 'install_module',
                        'payload': {'module_id': 'inventory'},
                        'command_jwt': 'jwt3'
                    }
                ]
            },
            status=200
        )

        # Add ack responses
        for cmd_id in ['cmd-1', 'cmd-2', 'cmd-3']:
            responses.add(
                responses.POST,
                f'https://cloud.erplora.com/api/hubs/me/commands/{cmd_id}/ack/',
                json={'success': True},
                status=200
            )

        from apps.sync.services.cloud_api import CloudAPIService

        service = CloudAPIService()
        commands = service.get_pending_commands()

        assert len(commands) == 3

        # Execute in order
        execution_order = []
        for cmd in commands:
            service.acknowledge_command(cmd['id'], 'completed')
            execution_order.append(cmd['id'])

        assert execution_order == ['cmd-1', 'cmd-2', 'cmd-3']


class TestJWTRefreshFlow:
    """E2E tests for JWT token handling."""

    @responses.activate
    def test_expired_jwt_triggers_401(self, hub_config, mock_settings):
        """Test expired JWT returns 401."""
        from apps.sync.services.cloud_api import CloudAPIService, CloudAPIError

        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/heartbeat/',
            json={'error': 'Token expired'},
            status=401
        )

        service = CloudAPIService()

        with pytest.raises(CloudAPIError) as exc_info:
            service.send_heartbeat()

        assert exc_info.value.status_code == 401

    @responses.activate
    def test_fetch_public_key_for_command_verification(self, hub_config, mock_settings):
        """Test fetching public key from Cloud."""
        hub_config.get_solo.return_value.cloud_public_key = ''

        responses.add(
            responses.GET,
            'https://cloud.erplora.com/api/auth/public-key/',
            json={
                'public_key': '-----BEGIN PUBLIC KEY-----\nMIIBIjANBg...\n-----END PUBLIC KEY-----'
            },
            status=200
        )

        from apps.sync.services.cloud_api import CloudAPIService

        service = CloudAPIService()
        key = service._get_public_key()

        assert key is not None
        assert 'BEGIN PUBLIC KEY' in key


class TestConfigSyncFlow:
    """E2E tests for configuration synchronization."""

    @responses.activate
    def test_config_sync_command_flow(self, hub_config, mock_settings):
        """Test configuration sync command execution."""
        responses.add(
            responses.GET,
            'https://cloud.erplora.com/api/hubs/me/commands/',
            json={
                'commands': [
                    {
                        'id': 'sync-config-1',
                        'type': 'sync_config',
                        'payload': {
                            'config': {
                                'currency': 'USD',
                                'timezone': 'America/New_York'
                            }
                        },
                        'command_jwt': 'sync.jwt'
                    }
                ]
            },
            status=200
        )

        responses.add(
            responses.POST,
            'https://cloud.erplora.com/api/hubs/me/commands/sync-config-1/ack/',
            json={'success': True},
            status=200
        )

        from apps.sync.services.cloud_api import CloudAPIService
        from apps.sync.services.heartbeat import HeartbeatService

        cloud_api = CloudAPIService()

        # Mock JWT verification to pass
        with patch.object(cloud_api, 'verify_command_jwt', return_value={'type': 'hub_command', 'hub_id': 'e2e-test-hub-id'}):
            heartbeat = HeartbeatService(cloud_api=cloud_api)

            # Poll and execute commands
            commands = cloud_api.get_pending_commands()
            assert len(commands) == 1

            for cmd in commands:
                heartbeat._execute_command(cmd)

            # Verify ack was sent
            assert len(responses.calls) == 2
            ack_request = responses.calls[1].request
            body = json.loads(ack_request.body)
            assert body['status'] == 'completed'
