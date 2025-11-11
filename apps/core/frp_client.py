"""
FRP Client Service for CPOS Hub.

Manages the FRP (Fast Reverse Proxy) client connection to Cloud.
Allows remote access to the Hub through secure tunnel.
"""
import os
import sys
import logging
import subprocess
import platform
from pathlib import Path
from typing import Optional
import time

from django.conf import settings

from apps.configuration.models import HubConfig


logger = logging.getLogger(__name__)


class FRPClientError(Exception):
    """Exception raised for FRP client errors"""
    pass


class FRPClient:
    """
    FRP Client service that establishes tunnel connection to Cloud.

    The client:
    1. Loads tunnel credentials from HubConfig (hub_id, tunnel_port, tunnel_token)
    2. Generates frpc.toml configuration file
    3. Launches frpc binary as subprocess
    4. Monitors connection status
    5. Handles reconnection

    Usage:
        client = FRPClient()
        client.start()  # Start tunnel
        client.is_running()  # Check status
        client.stop()  # Stop tunnel
        client.restart()  # Restart tunnel
    """

    def __init__(self):
        """
        Initialize FRP client and load configuration from database.

        Raises:
            FRPClientError: If Hub is not configured
        """
        # Load configuration from database
        self.config = HubConfig.get_config()

        if not self.config.is_configured:
            raise FRPClientError("Hub is not configured. Run initial setup first.")

        # Load credentials
        self.hub_id = str(self.config.hub_id)
        self.tunnel_port = self.config.tunnel_port
        self.tunnel_token = self.config.tunnel_token

        # FRP server settings (from Django settings)
        self.server_addr = getattr(settings, 'FRP_SERVER_ADDR', 'localhost')
        self.server_port = getattr(settings, 'FRP_SERVER_PORT', 7100)
        self.auth_token = getattr(settings, 'FRP_AUTH_TOKEN', 'cpos-local-dev-token')

        # Local Hub Django server (from Django settings)
        self.local_port = getattr(settings, 'HUB_LOCAL_PORT', 8001)

        # Paths
        self.hub_dir = Path(__file__).parent.parent.parent
        self.config_dir = self.hub_dir / 'config'
        self.config_path = self.config_dir / 'frpc.toml'

        # Process reference
        self.process: Optional[subprocess.Popen] = None

        logger.info(f"FRP Client initialized for hub: {self.hub_id}")

    def get_frpc_binary_path(self) -> Path:
        """
        Get platform-specific frpc binary path.

        Returns:
            Path: Path to frpc binary

        Raises:
            FRPClientError: If binary not found
        """
        # Detect platform
        system = platform.system()

        if system == 'Windows':
            binary_name = 'frpc.exe'
        else:  # macOS or Linux
            binary_name = 'frpc'

        # Binary location
        if getattr(sys, 'frozen', False):
            # Running from PyInstaller bundle
            bin_dir = Path(sys._MEIPASS) / 'bin'
        else:
            # Development mode
            bin_dir = self.hub_dir / 'bin'

        binary_path = bin_dir / binary_name

        if not binary_path.exists():
            # Try alternative location (for development)
            binary_path = self.hub_dir / 'frpc' / binary_name

        logger.debug(f"FRP binary path: {binary_path}")
        return binary_path

    def generate_config(self, config_path: Optional[Path] = None) -> Path:
        """
        Generate frpc.toml configuration file.

        Args:
            config_path: Optional custom path for config file

        Returns:
            Path: Path to generated config file
        """
        if config_path is None:
            config_path = self.config_path

        # Ensure config directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate TOML configuration
        config_content = f"""# CPOS Hub - FRP Client Configuration
# Auto-generated - DO NOT EDIT MANUALLY

[common]
server_addr = "{self.server_addr}"
server_port = {self.server_port}
authentication_method = "token"
token = "{self.auth_token}"
authenticate_new_work_conns = false

# Hub tunnel
[{self.hub_id}]
type = "tcp"
local_ip = "127.0.0.1"
local_port = {self.local_port}
remote_port = {self.tunnel_port}
"""

        # Write configuration
        with open(config_path, 'w') as f:
            f.write(config_content)

        logger.info(f"Generated FRP config: {config_path}")
        return config_path

    def start(self) -> None:
        """
        Start the FRP client.

        Raises:
            FRPClientError: If client is already running or start fails
        """
        if self.is_running():
            raise FRPClientError("FRP client is already running")

        logger.info("Starting FRP client...")

        # Generate configuration
        self.generate_config()

        # Get binary path
        frpc_binary = self.get_frpc_binary_path()

        if not frpc_binary.exists():
            raise FRPClientError(f"FRP binary not found: {frpc_binary}")

        # Build command
        command = [
            str(frpc_binary),
            '-c', str(self.config_path)
        ]

        try:
            # Launch frpc process
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                # Detach from parent process
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == 'Windows' else 0,
                preexec_fn=None if platform.system() == 'Windows' else os.setpgrp,
            )

            # Wait a bit to check if process started successfully
            time.sleep(1)

            if self.process.poll() is not None:
                # Process died immediately
                stdout, stderr = self.process.communicate()
                error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
                raise FRPClientError(f"FRP client failed to start: {error_msg}")

            logger.info(f"✅ FRP client started (PID: {self.process.pid})")

        except Exception as e:
            logger.exception(f"Error starting FRP client: {e}")
            self.process = None
            raise FRPClientError(f"Failed to start FRP client: {e}")

    def stop(self) -> None:
        """
        Stop the FRP client gracefully.
        """
        if not self.process:
            logger.warning("FRP client is not running")
            return

        logger.info("Stopping FRP client...")

        try:
            # Terminate gracefully
            self.process.terminate()

            # Wait for graceful shutdown (max 5 seconds)
            try:
                self.process.wait(timeout=5)
                logger.info("✅ FRP client stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if still running
                logger.warning("FRP client did not stop gracefully, forcing kill...")
                self.process.kill()
                self.process.wait()
                logger.info("✅ FRP client killed")

        except Exception as e:
            logger.exception(f"Error stopping FRP client: {e}")

        finally:
            self.process = None

    def restart(self) -> None:
        """
        Restart the FRP client.
        """
        logger.info("Restarting FRP client...")
        self.stop()
        time.sleep(1)  # Brief pause between stop and start
        self.start()

    def is_running(self) -> bool:
        """
        Check if FRP client is running.

        Returns:
            bool: True if running, False otherwise
        """
        if not self.process:
            return False

        # Check if process is still alive
        return self.process.poll() is None

    def get_status(self) -> dict:
        """
        Get detailed status of FRP client.

        Returns:
            dict: Status information
        """
        running = self.is_running()

        status = {
            'running': running,
            'hub_id': self.hub_id,
            'tunnel_port': self.tunnel_port,
            'server': f"{self.server_addr}:{self.server_port}",
            'local_port': self.local_port,
        }

        if running and self.process:
            status['pid'] = self.process.pid

        return status

    def __del__(self):
        """Cleanup when client is destroyed"""
        # Only cleanup if object was fully initialized
        if hasattr(self, 'process') and self.is_running():
            logger.warning("FRP client still running during cleanup, stopping...")
            self.stop()


# Global instance (singleton)
# Initialize lazily to avoid errors during Django setup
_frp_client_instance: Optional[FRPClient] = None


def get_frp_client() -> FRPClient:
    """
    Get or create global FRP client instance.

    Returns:
        FRPClient: The global FRP client instance

    Raises:
        FRPClientError: If Hub is not configured
    """
    global _frp_client_instance

    if _frp_client_instance is None:
        _frp_client_instance = FRPClient()

    return _frp_client_instance
