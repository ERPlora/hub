"""
Heartbeat Service for Hub-to-Cloud communication.

Sends periodic heartbeats to Cloud to indicate Hub is online.
Also polls for pending commands and executes them.
"""
import logging
import threading
import time
from typing import Optional, Callable, Dict, Any

from django.conf import settings

from .cloud_api import CloudAPIService, CloudAPIError, get_cloud_api

logger = logging.getLogger(__name__)


class HeartbeatService:
    """
    Background service for heartbeat and command polling.

    Features:
    - Periodic heartbeat every 60 seconds (configurable)
    - Command polling every 5 minutes (configurable)
    - Automatic command execution
    - Graceful shutdown

    Usage:
        # Start heartbeat service
        service = HeartbeatService()
        service.start()

        # Stop service
        service.stop()
    """

    DEFAULT_HEARTBEAT_INTERVAL = 60  # seconds
    DEFAULT_COMMAND_POLL_INTERVAL = 300  # 5 minutes

    def __init__(
        self,
        heartbeat_interval: int = None,
        command_poll_interval: int = None,
        cloud_api: CloudAPIService = None
    ):
        """
        Initialize heartbeat service.

        Args:
            heartbeat_interval: Heartbeat interval in seconds
            command_poll_interval: Command polling interval in seconds
            cloud_api: CloudAPIService instance (optional)
        """
        self.heartbeat_interval = (
            heartbeat_interval or
            getattr(settings, 'HEARTBEAT_INTERVAL', self.DEFAULT_HEARTBEAT_INTERVAL)
        )
        self.command_poll_interval = (
            command_poll_interval or
            getattr(settings, 'COMMAND_POLL_INTERVAL', self.DEFAULT_COMMAND_POLL_INTERVAL)
        )
        self.cloud_api = cloud_api or get_cloud_api()

        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._command_thread: Optional[threading.Thread] = None

        # Command handlers registry
        self._command_handlers: Dict[str, Callable] = {}

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default command handlers."""
        self.register_handler('install_module', self._handle_install_module)
        self.register_handler('update_module', self._handle_update_module)
        self.register_handler('remove_module', self._handle_remove_module)
        self.register_handler('sync_config', self._handle_sync_config)

    def register_handler(self, command_type: str, handler: Callable):
        """
        Register a command handler.

        Args:
            command_type: Type of command to handle
            handler: Callable that takes (payload) and returns (success, result, error)
        """
        self._command_handlers[command_type] = handler
        logger.debug(f"[HEARTBEAT] Registered handler for {command_type}")

    def start(self):
        """Start heartbeat and command polling threads."""
        if self._running:
            logger.warning("[HEARTBEAT] Service already running")
            return

        if not self.cloud_api.is_configured:
            logger.warning("[HEARTBEAT] Hub not configured, service not started")
            return

        self._running = True

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="HeartbeatThread"
        )
        self._heartbeat_thread.start()

        # Start command polling thread
        self._command_thread = threading.Thread(
            target=self._command_poll_loop,
            daemon=True,
            name="CommandPollThread"
        )
        self._command_thread.start()

        logger.info(
            f"[HEARTBEAT] Service started "
            f"(heartbeat={self.heartbeat_interval}s, "
            f"commands={self.command_poll_interval}s)"
        )

    def stop(self):
        """Stop heartbeat service."""
        if not self._running:
            return

        self._running = False
        logger.info("[HEARTBEAT] Service stopping...")

        # Wait for threads to finish
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)

        if self._command_thread and self._command_thread.is_alive():
            self._command_thread.join(timeout=5)

        logger.info("[HEARTBEAT] Service stopped")

    def _heartbeat_loop(self):
        """Heartbeat thread main loop."""
        while self._running:
            try:
                self._send_heartbeat()
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error in heartbeat loop: {str(e)}")

            # Sleep in small intervals to allow quick shutdown
            for _ in range(self.heartbeat_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _command_poll_loop(self):
        """Command polling thread main loop."""
        # Initial delay before first poll
        time.sleep(10)

        while self._running:
            try:
                self._poll_commands()
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error in command poll loop: {str(e)}")

            # Sleep in small intervals
            for _ in range(self.command_poll_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _send_heartbeat(self):
        """Send heartbeat to Cloud."""
        try:
            metadata = self._get_heartbeat_metadata()
            response = self.cloud_api.send_heartbeat(metadata)
            logger.debug(f"[HEARTBEAT] Sent successfully: {response}")

        except CloudAPIError as e:
            logger.warning(f"[HEARTBEAT] Failed to send: {e.message}")

    def _get_heartbeat_metadata(self) -> Dict[str, Any]:
        """Build heartbeat metadata."""
        from apps.configuration.models import HubConfig

        config = HubConfig.get_solo()

        # Get installed modules
        installed_modules = self._get_installed_modules()

        return {
            'version': getattr(settings, 'HUB_VERSION', '1.0.0'),
            'modules': installed_modules,
            'status': 'healthy',
            'configured': config.is_configured,
        }

    def _get_installed_modules(self) -> list:
        """Get list of installed module IDs."""
        try:
            from apps.modules_runtime.module_loader import discover_modules
            modules = discover_modules(include_inactive=False)
            return [m['module_id'] for m in modules]
        except Exception:
            return []

    def _poll_commands(self):
        """Poll and execute pending commands."""
        try:
            commands = self.cloud_api.get_pending_commands()

            if not commands:
                logger.debug("[HEARTBEAT] No pending commands")
                return

            logger.info(f"[HEARTBEAT] Received {len(commands)} pending commands")

            for cmd in commands:
                self._execute_command(cmd)

        except CloudAPIError as e:
            logger.warning(f"[HEARTBEAT] Failed to poll commands: {e.message}")

    def _execute_command(self, command: Dict[str, Any]):
        """
        Execute a single command.

        Args:
            command: Command data from Cloud
        """
        command_id = command.get('id')
        command_type = command.get('type')
        payload = command.get('payload', {})
        command_jwt = command.get('command_jwt')

        logger.info(f"[HEARTBEAT] Executing command: {command_type} ({command_id})")

        # Verify command JWT
        if command_jwt:
            verified = self.cloud_api.verify_command_jwt(command_jwt)
            if not verified:
                logger.warning(
                    f"[HEARTBEAT] Command JWT verification failed: {command_id}"
                )
                self._ack_command(command_id, 'failed', error='JWT verification failed')
                return

        # Get handler
        handler = self._command_handlers.get(command_type)

        if not handler:
            logger.warning(f"[HEARTBEAT] No handler for command type: {command_type}")
            self._ack_command(
                command_id,
                'failed',
                error=f'Unknown command type: {command_type}'
            )
            return

        # Execute handler
        try:
            success, result, error = handler(payload)

            if success:
                self._ack_command(command_id, 'completed', result=result)
                logger.info(f"[HEARTBEAT] Command completed: {command_id}")
            else:
                self._ack_command(command_id, 'failed', error=error)
                logger.warning(f"[HEARTBEAT] Command failed: {command_id} - {error}")

        except Exception as e:
            logger.error(f"[HEARTBEAT] Command execution error: {str(e)}")
            self._ack_command(command_id, 'failed', error=str(e))

    def _ack_command(
        self,
        command_id: str,
        status: str,
        result: Dict = None,
        error: str = None
    ):
        """Acknowledge command execution to Cloud."""
        try:
            self.cloud_api.acknowledge_command(
                command_id=command_id,
                status=status,
                result=result,
                error=error
            )
        except CloudAPIError as e:
            logger.error(f"[HEARTBEAT] Failed to ack command {command_id}: {e.message}")

    # =========================================================================
    # Default Command Handlers
    # =========================================================================

    def _handle_install_module(self, payload: Dict) -> tuple:
        """Handle install_module command."""
        module_id = payload.get('module_id')
        version = payload.get('version')

        if not module_id:
            return False, None, "Missing module_id"

        # TODO: Implement module installation
        logger.info(f"[COMMAND] Install module: {module_id} v{version}")

        # For now, return success placeholder
        return True, {'installed': module_id}, None

    def _handle_update_module(self, payload: Dict) -> tuple:
        """Handle update_module command."""
        module_id = payload.get('module_id')
        version = payload.get('version')

        if not module_id:
            return False, None, "Missing module_id"

        # TODO: Implement module update
        logger.info(f"[COMMAND] Update module: {module_id} v{version}")

        return True, {'updated': module_id}, None

    def _handle_remove_module(self, payload: Dict) -> tuple:
        """Handle remove_module command."""
        module_id = payload.get('module_id')

        if not module_id:
            return False, None, "Missing module_id"

        # TODO: Implement module removal
        logger.info(f"[COMMAND] Remove module: {module_id}")

        return True, {'removed': module_id}, None

    def _handle_sync_config(self, payload: Dict) -> tuple:
        """Handle sync_config command."""
        # TODO: Implement config sync
        logger.info("[COMMAND] Sync config")

        return True, {'synced': True}, None


# Global instance for app startup
_heartbeat_service: Optional[HeartbeatService] = None


def get_heartbeat_service() -> HeartbeatService:
    """Get or create HeartbeatService instance."""
    global _heartbeat_service
    if _heartbeat_service is None:
        _heartbeat_service = HeartbeatService()
    return _heartbeat_service


def start_heartbeat_service():
    """Start the heartbeat service (call from AppConfig.ready())."""
    service = get_heartbeat_service()
    service.start()


def stop_heartbeat_service():
    """Stop the heartbeat service."""
    global _heartbeat_service
    if _heartbeat_service:
        _heartbeat_service.stop()
        _heartbeat_service = None
