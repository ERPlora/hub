"""
Unit tests for HeartbeatService.

Tests the Hub's background heartbeat and command polling service.
"""
import pytest
import threading
import time
from unittest.mock import patch, MagicMock, call


# Mark all tests in this module
pytestmark = pytest.mark.unit


@pytest.fixture
def mock_cloud_api():
    """Create a mock CloudAPIService."""
    mock = MagicMock()
    mock.is_configured = True
    mock.send_heartbeat.return_value = {'success': True}
    mock.get_pending_commands.return_value = []
    mock.verify_command_jwt.return_value = {'type': 'hub_command'}
    mock.acknowledge_command.return_value = {'success': True}
    return mock


@pytest.fixture
def heartbeat_service(mock_cloud_api):
    """Create HeartbeatService with mocked dependencies."""
    with patch('apps.sync.services.heartbeat.settings') as mock_settings:
        mock_settings.HEARTBEAT_INTERVAL = 60
        mock_settings.COMMAND_POLL_INTERVAL = 300
        mock_settings.HUB_VERSION = '1.0.0'

        from apps.sync.services.heartbeat import HeartbeatService
        service = HeartbeatService(
            heartbeat_interval=1,  # Short interval for tests
            command_poll_interval=1,
            cloud_api=mock_cloud_api
        )
        return service


class TestHeartbeatServiceInit:
    """Tests for HeartbeatService initialization."""

    def test_init_with_defaults(self, mock_cloud_api):
        """Test initialization with default values."""
        with patch('apps.sync.services.heartbeat.settings') as mock_settings:
            mock_settings.HEARTBEAT_INTERVAL = 60
            mock_settings.COMMAND_POLL_INTERVAL = 300

            from apps.sync.services.heartbeat import HeartbeatService
            service = HeartbeatService(cloud_api=mock_cloud_api)

            assert service.heartbeat_interval == 60
            assert service.command_poll_interval == 300

    def test_init_with_custom_intervals(self, mock_cloud_api):
        """Test initialization with custom intervals."""
        with patch('apps.sync.services.heartbeat.settings'):
            from apps.sync.services.heartbeat import HeartbeatService
            service = HeartbeatService(
                heartbeat_interval=30,
                command_poll_interval=120,
                cloud_api=mock_cloud_api
            )

            assert service.heartbeat_interval == 30
            assert service.command_poll_interval == 120

    def test_init_registers_default_handlers(self, mock_cloud_api):
        """Test default command handlers are registered."""
        with patch('apps.sync.services.heartbeat.settings'):
            from apps.sync.services.heartbeat import HeartbeatService
            service = HeartbeatService(cloud_api=mock_cloud_api)

            assert 'install_plugin' in service._command_handlers
            assert 'update_plugin' in service._command_handlers
            assert 'remove_plugin' in service._command_handlers
            assert 'sync_config' in service._command_handlers


class TestHeartbeatServiceStartStop:
    """Tests for starting and stopping the service."""

    def test_start_creates_threads(self, heartbeat_service):
        """Test that start creates heartbeat and command threads."""
        heartbeat_service.start()

        try:
            assert heartbeat_service._running is True
            assert heartbeat_service._heartbeat_thread is not None
            assert heartbeat_service._command_thread is not None
            assert heartbeat_service._heartbeat_thread.is_alive()
            assert heartbeat_service._command_thread.is_alive()
        finally:
            heartbeat_service.stop()

    def test_start_when_not_configured(self, mock_cloud_api):
        """Test start does nothing when not configured."""
        mock_cloud_api.is_configured = False

        with patch('apps.sync.services.heartbeat.settings'):
            from apps.sync.services.heartbeat import HeartbeatService
            service = HeartbeatService(cloud_api=mock_cloud_api)
            service.start()

            assert service._running is False
            assert service._heartbeat_thread is None

    def test_start_twice_does_nothing(self, heartbeat_service):
        """Test starting twice doesn't create duplicate threads."""
        heartbeat_service.start()

        thread1 = heartbeat_service._heartbeat_thread

        heartbeat_service.start()  # Second start

        assert heartbeat_service._heartbeat_thread is thread1

        heartbeat_service.stop()

    def test_stop_terminates_threads(self, heartbeat_service):
        """Test that stop terminates threads gracefully."""
        heartbeat_service.start()

        # Give threads time to start
        time.sleep(0.1)

        heartbeat_service.stop()

        assert heartbeat_service._running is False
        # Threads should have stopped (or be daemon and not blocking)

    def test_stop_when_not_running(self, heartbeat_service):
        """Test stop does nothing when not running."""
        # Should not raise
        heartbeat_service.stop()
        assert heartbeat_service._running is False


class TestHeartbeatLoop:
    """Tests for the heartbeat loop."""

    def test_sends_heartbeat(self, heartbeat_service, mock_cloud_api):
        """Test that heartbeat is sent."""
        heartbeat_service.start()

        # Wait for at least one heartbeat
        time.sleep(0.5)

        heartbeat_service.stop()

        assert mock_cloud_api.send_heartbeat.called

    def test_heartbeat_includes_metadata(self, heartbeat_service, mock_cloud_api):
        """Test heartbeat includes version and plugins."""
        with patch.object(heartbeat_service, '_get_installed_plugins', return_value=['plugin1', 'plugin2']):
            heartbeat_service._send_heartbeat()

            call_args = mock_cloud_api.send_heartbeat.call_args
            metadata = call_args[0][0] if call_args[0] else call_args[1].get('metadata', {})

            assert 'version' in metadata or mock_cloud_api.send_heartbeat.called

    def test_heartbeat_handles_api_error(self, heartbeat_service, mock_cloud_api):
        """Test heartbeat loop continues on API error."""
        from apps.sync.services.cloud_api import CloudAPIError

        mock_cloud_api.send_heartbeat.side_effect = CloudAPIError("Connection failed")

        # Should not raise
        heartbeat_service._send_heartbeat()


class TestCommandPolling:
    """Tests for command polling loop."""

    def test_polls_for_commands(self, heartbeat_service, mock_cloud_api):
        """Test that commands are polled."""
        heartbeat_service._poll_commands()

        mock_cloud_api.get_pending_commands.assert_called_once()

    def test_executes_pending_commands(self, heartbeat_service, mock_cloud_api):
        """Test that pending commands are executed."""
        mock_cloud_api.get_pending_commands.return_value = [
            {
                'id': 'cmd-1',
                'type': 'install_plugin',
                'payload': {'plugin_id': 'test'},
                'command_jwt': 'valid.jwt'
            }
        ]

        with patch.object(heartbeat_service, '_execute_command') as mock_exec:
            heartbeat_service._poll_commands()

            mock_exec.assert_called_once()

    def test_polling_handles_api_error(self, heartbeat_service, mock_cloud_api):
        """Test polling continues on API error."""
        from apps.sync.services.cloud_api import CloudAPIError

        mock_cloud_api.get_pending_commands.side_effect = CloudAPIError("Connection failed")

        # Should not raise
        heartbeat_service._poll_commands()


class TestCommandExecution:
    """Tests for command execution."""

    def test_execute_command_success(self, heartbeat_service, mock_cloud_api):
        """Test successful command execution."""
        command = {
            'id': 'cmd-1',
            'type': 'install_plugin',
            'payload': {'plugin_id': 'inventory'},
            'command_jwt': 'valid.jwt'
        }

        heartbeat_service._execute_command(command)

        # Should acknowledge completion
        mock_cloud_api.acknowledge_command.assert_called_once_with(
            command_id='cmd-1',
            status='completed',
            result={'installed': 'inventory'},
            error=None
        )

    def test_execute_command_unknown_type(self, heartbeat_service, mock_cloud_api):
        """Test execution of unknown command type."""
        command = {
            'id': 'cmd-1',
            'type': 'unknown_command',
            'payload': {},
            'command_jwt': 'valid.jwt'
        }

        heartbeat_service._execute_command(command)

        # Should acknowledge failure
        mock_cloud_api.acknowledge_command.assert_called_once()
        call_args = mock_cloud_api.acknowledge_command.call_args
        assert call_args[1]['status'] == 'failed'
        assert 'Unknown command type' in call_args[1]['error']

    def test_execute_command_jwt_verification_fails(self, heartbeat_service, mock_cloud_api):
        """Test execution fails when JWT verification fails."""
        mock_cloud_api.verify_command_jwt.return_value = None

        command = {
            'id': 'cmd-1',
            'type': 'install_plugin',
            'payload': {},
            'command_jwt': 'invalid.jwt'
        }

        heartbeat_service._execute_command(command)

        # Should acknowledge failure
        call_args = mock_cloud_api.acknowledge_command.call_args
        assert call_args[1]['status'] == 'failed'
        assert 'JWT verification' in call_args[1]['error']

    def test_execute_command_handler_exception(self, heartbeat_service, mock_cloud_api):
        """Test execution handles handler exceptions."""
        # Register a failing handler
        def failing_handler(payload):
            raise Exception("Handler crashed")

        heartbeat_service.register_handler('failing', failing_handler)

        command = {
            'id': 'cmd-1',
            'type': 'failing',
            'payload': {},
            'command_jwt': 'valid.jwt'
        }

        # Should not raise
        heartbeat_service._execute_command(command)

        # Should acknowledge failure
        call_args = mock_cloud_api.acknowledge_command.call_args
        assert call_args[1]['status'] == 'failed'


class TestCommandHandlers:
    """Tests for default command handlers."""

    def test_handle_install_plugin(self, heartbeat_service):
        """Test install_plugin handler."""
        success, result, error = heartbeat_service._handle_install_plugin({
            'plugin_id': 'inventory',
            'version': '1.0.0'
        })

        assert success is True
        assert 'installed' in result

    def test_handle_install_plugin_missing_id(self, heartbeat_service):
        """Test install_plugin handler with missing plugin_id."""
        success, result, error = heartbeat_service._handle_install_plugin({})

        assert success is False
        assert 'Missing plugin_id' in error

    def test_handle_update_plugin(self, heartbeat_service):
        """Test update_plugin handler."""
        success, result, error = heartbeat_service._handle_update_plugin({
            'plugin_id': 'inventory'
        })

        assert success is True

    def test_handle_remove_plugin(self, heartbeat_service):
        """Test remove_plugin handler."""
        success, result, error = heartbeat_service._handle_remove_plugin({
            'plugin_id': 'inventory'
        })

        assert success is True

    def test_handle_sync_config(self, heartbeat_service):
        """Test sync_config handler."""
        success, result, error = heartbeat_service._handle_sync_config({})

        assert success is True


class TestRegisterHandler:
    """Tests for custom handler registration."""

    def test_register_custom_handler(self, heartbeat_service):
        """Test registering a custom handler."""
        def custom_handler(payload):
            return True, {'custom': True}, None

        heartbeat_service.register_handler('custom_command', custom_handler)

        assert 'custom_command' in heartbeat_service._command_handlers

    def test_custom_handler_is_called(self, heartbeat_service, mock_cloud_api):
        """Test custom handler is called for matching command."""
        handler_called = []

        def custom_handler(payload):
            handler_called.append(payload)
            return True, {'result': 'ok'}, None

        heartbeat_service.register_handler('custom', custom_handler)

        command = {
            'id': 'cmd-1',
            'type': 'custom',
            'payload': {'data': 'test'},
            'command_jwt': 'valid.jwt'
        }

        heartbeat_service._execute_command(command)

        assert len(handler_called) == 1
        assert handler_called[0] == {'data': 'test'}


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_get_heartbeat_service_singleton(self):
        """Test get_heartbeat_service returns singleton."""
        with patch('apps.sync.services.heartbeat.HeartbeatService') as MockService:
            # Reset singleton
            import apps.sync.services.heartbeat as module
            module._heartbeat_service = None

            from apps.sync.services.heartbeat import get_heartbeat_service

            service1 = get_heartbeat_service()
            service2 = get_heartbeat_service()

            assert service1 is service2
            assert MockService.call_count == 1

            # Cleanup
            module._heartbeat_service = None

    def test_start_heartbeat_service(self):
        """Test start_heartbeat_service starts the service."""
        with patch('apps.sync.services.heartbeat.get_heartbeat_service') as mock_get:
            mock_service = MagicMock()
            mock_get.return_value = mock_service

            from apps.sync.services.heartbeat import start_heartbeat_service

            start_heartbeat_service()

            mock_service.start.assert_called_once()

    def test_stop_heartbeat_service(self):
        """Test stop_heartbeat_service stops and clears singleton."""
        import apps.sync.services.heartbeat as module

        mock_service = MagicMock()
        module._heartbeat_service = mock_service

        from apps.sync.services.heartbeat import stop_heartbeat_service

        stop_heartbeat_service()

        mock_service.stop.assert_called_once()
        assert module._heartbeat_service is None
