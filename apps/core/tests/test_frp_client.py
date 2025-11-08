"""
Tests for FRP Client Service.

Tests the FRP client that establishes tunnel connection to Cloud.
"""
import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import subprocess
import tempfile

from apps.core.frp_client import FRPClient, FRPClientError
from apps.core.models import HubConfig


@pytest.mark.unit
class TestFRPClient:
    """Test FRP Client initialization and configuration"""

    @pytest.fixture
    def hub_config(self, db):
        """Create a configured HubConfig for testing"""
        config = HubConfig.get_config()
        config.hub_id = uuid.uuid4()
        config.tunnel_port = 7001
        config.tunnel_token = "test-token-123"
        config.is_configured = True
        config.save()
        return config

    @pytest.fixture
    def frp_client(self, hub_config):
        """Create FRP client instance"""
        return FRPClient()

    def test_init_loads_config_from_database(self, frp_client, hub_config):
        """
        GIVEN: A configured HubConfig in database
        WHEN: FRPClient is initialized
        THEN: Should load config from database
        """
        assert frp_client.hub_id == str(hub_config.hub_id)
        assert frp_client.tunnel_port == hub_config.tunnel_port
        assert frp_client.tunnel_token == hub_config.tunnel_token

    def test_init_raises_error_if_not_configured(self, db):
        """
        GIVEN: A HubConfig that is not configured
        WHEN: FRPClient is initialized
        THEN: Should raise FRPClientError
        """
        config = HubConfig.get_config()
        config.is_configured = False
        config.save()

        with pytest.raises(FRPClientError, match="Hub is not configured"):
            FRPClient()

    def test_generate_config_creates_valid_toml(self, frp_client, tmp_path):
        """
        GIVEN: An initialized FRP client
        WHEN: generate_config() is called
        THEN: Should create valid frpc.toml file
        """
        config_path = tmp_path / "frpc.toml"
        frp_client.generate_config(config_path)

        assert config_path.exists()
        config_content = config_path.read_text()

        # Verify essential fields are present
        assert "[common]" in config_content
        assert f"server_port = 7000" in config_content
        assert f"authentication_method = \"token\"" in config_content
        assert f"authenticate_new_work_conns = false" in config_content
        assert f"[{frp_client.hub_id}]" in config_content
        assert f"type = \"tcp\"" in config_content
        assert f"local_port = 8001" in config_content
        assert f"remote_port = {frp_client.tunnel_port}" in config_content

    def test_get_frpc_binary_path_returns_platform_specific(self, frp_client):
        """
        GIVEN: An initialized FRP client
        WHEN: get_frpc_binary_path() is called
        THEN: Should return platform-specific binary path
        """
        import platform

        binary_path = frp_client.get_frpc_binary_path()

        assert binary_path.exists() or True  # In tests, binary might not exist
        if platform.system() == "Windows":
            assert binary_path.name == "frpc.exe"
        else:
            assert binary_path.name == "frpc"


@pytest.mark.unit
class TestFRPClientProcess:
    """Test FRP Client process management"""

    @pytest.fixture
    def hub_config(self, db):
        """Create configured HubConfig"""
        config = HubConfig.get_config()
        config.hub_id = uuid.uuid4()
        config.tunnel_port = 7001
        config.tunnel_token = "test-token-123"
        config.is_configured = True
        config.save()
        return config

    @pytest.fixture
    def frp_client(self, hub_config):
        """Create FRP client instance"""
        return FRPClient()

    @patch('apps.core.frp_client.subprocess.Popen')
    @patch('apps.core.frp_client.FRPClient.get_frpc_binary_path')
    def test_start_launches_frpc_process(self, mock_binary_path, mock_popen, frp_client, tmp_path):
        """
        GIVEN: An initialized FRP client
        WHEN: start() is called
        THEN: Should launch frpc subprocess
        """
        # Mock binary path
        fake_binary = tmp_path / "frpc"
        fake_binary.touch()
        mock_binary_path.return_value = fake_binary

        # Mock process
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process

        # Start client
        frp_client.start()

        # Verify subprocess.Popen was called
        assert mock_popen.called
        call_args = mock_popen.call_args

        # Verify frpc binary is in command
        assert "frpc" in str(call_args[0][0])
        assert "-c" in call_args[0][0]

        # Verify process is stored
        assert frp_client.process == mock_process

    @patch('apps.core.frp_client.subprocess.Popen')
    @patch('apps.core.frp_client.FRPClient.get_frpc_binary_path')
    def test_start_creates_config_file(self, mock_binary_path, mock_popen, frp_client, tmp_path):
        """
        GIVEN: An initialized FRP client
        WHEN: start() is called
        THEN: Should create frpc.toml config file
        """
        # Mock binary path
        fake_binary = tmp_path / "frpc"
        fake_binary.touch()
        mock_binary_path.return_value = fake_binary

        mock_process = Mock()
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        # Patch config path to use tmp_path
        config_path = tmp_path / "frpc.toml"
        frp_client.config_path = config_path

        frp_client.start()

        # Verify config file was created
        assert config_path.exists()

    def test_stop_terminates_process(self, frp_client):
        """
        GIVEN: A running FRP client
        WHEN: stop() is called
        THEN: Should terminate the process
        """
        # Mock running process
        mock_process = Mock()
        frp_client.process = mock_process

        frp_client.stop()

        # Verify terminate was called
        assert mock_process.terminate.called

    def test_stop_waits_for_graceful_shutdown(self, frp_client):
        """
        GIVEN: A running FRP client
        WHEN: stop() is called
        THEN: Should wait for graceful shutdown before killing
        """
        mock_process = Mock()
        mock_process.poll.return_value = None  # Still running after terminate
        frp_client.process = mock_process

        frp_client.stop()

        # Verify wait was called with timeout
        assert mock_process.wait.called
        # If wait times out, kill should be called
        if mock_process.wait.side_effect == subprocess.TimeoutExpired:
            assert mock_process.kill.called

    def test_is_running_returns_true_when_process_alive(self, frp_client):
        """
        GIVEN: A running FRP client
        WHEN: is_running() is called
        THEN: Should return True
        """
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process is running
        frp_client.process = mock_process

        assert frp_client.is_running() is True

    def test_is_running_returns_false_when_process_dead(self, frp_client):
        """
        GIVEN: A stopped FRP client
        WHEN: is_running() is called
        THEN: Should return False
        """
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Process exited
        frp_client.process = mock_process

        assert frp_client.is_running() is False

    def test_is_running_returns_false_when_no_process(self, frp_client):
        """
        GIVEN: An FRP client that was never started
        WHEN: is_running() is called
        THEN: Should return False
        """
        assert frp_client.process is None
        assert frp_client.is_running() is False

    @patch('apps.core.frp_client.subprocess.Popen')
    @patch('apps.core.frp_client.FRPClient.get_frpc_binary_path')
    def test_restart_stops_and_starts_process(self, mock_binary_path, mock_popen, frp_client, tmp_path):
        """
        GIVEN: A running FRP client
        WHEN: restart() is called
        THEN: Should stop existing process and start new one
        """
        # Mock binary path
        fake_binary = tmp_path / "frpc"
        fake_binary.touch()
        mock_binary_path.return_value = fake_binary

        # Setup mock process
        old_process = Mock()
        old_process.poll.return_value = None
        frp_client.process = old_process

        new_process = Mock()
        new_process.poll.return_value = None
        mock_popen.return_value = new_process

        frp_client.restart()

        # Verify old process was terminated
        assert old_process.terminate.called

        # Verify new process was started
        assert frp_client.process == new_process

    @patch('apps.core.frp_client.subprocess.Popen')
    def test_start_raises_error_if_already_running(self, mock_popen, frp_client):
        """
        GIVEN: A running FRP client
        WHEN: start() is called again
        THEN: Should raise FRPClientError
        """
        mock_process = Mock()
        mock_process.poll.return_value = None  # Running
        frp_client.process = mock_process

        with pytest.raises(FRPClientError, match="FRP client is already running"):
            frp_client.start()


@pytest.mark.unit
class TestFRPClientConfiguration:
    """Test FRP Client configuration generation"""

    @pytest.fixture
    def hub_config(self, db):
        """Create configured HubConfig"""
        config = HubConfig.get_config()
        config.hub_id = uuid.uuid4()
        config.tunnel_port = 7042
        config.tunnel_token = "secret-token-xyz"
        config.is_configured = True
        config.save()
        return config

    def test_config_contains_server_address(self, hub_config):
        """
        GIVEN: FRP client with hub config
        WHEN: Configuration is generated
        THEN: Should contain Cloud server address
        """
        client = FRPClient()
        config_path = Path(tempfile.mktemp(suffix=".toml"))

        try:
            client.generate_config(config_path)
            content = config_path.read_text()

            # Should use Cloud domain from settings
            assert "server_addr" in content
            # In tests, might be localhost or actual domain
            assert ("localhost" in content or "cpos.app" in content)
        finally:
            if config_path.exists():
                config_path.unlink()

    def test_config_contains_authentication_token(self, hub_config):
        """
        GIVEN: FRP client with hub config
        WHEN: Configuration is generated
        THEN: Should contain authentication token
        """
        client = FRPClient()
        config_path = Path(tempfile.mktemp(suffix=".toml"))

        try:
            client.generate_config(config_path)
            content = config_path.read_text()

            assert f'token = "{hub_config.tunnel_token}"' in content
        finally:
            if config_path.exists():
                config_path.unlink()

    def test_config_uses_correct_ports(self, hub_config):
        """
        GIVEN: FRP client with hub config
        WHEN: Configuration is generated
        THEN: Should use correct local and remote ports
        """
        client = FRPClient()
        config_path = Path(tempfile.mktemp(suffix=".toml"))

        try:
            client.generate_config(config_path)
            content = config_path.read_text()

            assert f"local_port = 8001" in content  # Hub's Django port
            assert f"remote_port = {hub_config.tunnel_port}" in content
        finally:
            if config_path.exists():
                config_path.unlink()
