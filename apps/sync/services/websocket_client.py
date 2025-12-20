"""
WebSocket Client for Hub-to-Cloud real-time communication.

Maintains persistent WebSocket connection to Cloud for:
- Heartbeat (online/offline status)
- Receiving commands from Cloud (install module, sync config)
- Sending events to Cloud (module installed, user sync)
"""
import json
import logging
import threading
import time
from typing import Optional, Callable, Dict, Any

from django.conf import settings

logger = logging.getLogger(__name__)


class WebSocketClient:
    """
    WebSocket client for Hub-to-Cloud communication.

    Features:
    - Auto-reconnect on disconnect
    - Heartbeat every 30 seconds
    - Command handlers registry
    - Thread-safe message sending

    Usage:
        client = WebSocketClient()
        client.register_handler('install_module', handle_install)
        client.start()
    """

    HEARTBEAT_INTERVAL = 30  # seconds
    RECONNECT_DELAY = 5  # seconds
    MAX_RECONNECT_DELAY = 60  # seconds

    def __init__(self):
        self.ws = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._reconnect_delay = self.RECONNECT_DELAY

        # Command handlers
        self._handlers: Dict[str, Callable] = {}
        self._register_default_handlers()

        # Get config
        self._hub_id = None
        self._hub_jwt = None
        self._cloud_ws_url = None

    def _load_config(self):
        """Load configuration from HubConfig."""
        from apps.configuration.models import HubConfig

        config = HubConfig.get_solo()
        self._hub_id = str(config.hub_id) if config.hub_id else None
        self._hub_jwt = config.hub_jwt

        # Build WebSocket URL
        cloud_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
        # Convert https:// to wss:// or http:// to ws://
        if cloud_url.startswith('https://'):
            ws_url = cloud_url.replace('https://', 'wss://')
        else:
            ws_url = cloud_url.replace('http://', 'ws://')

        self._cloud_ws_url = f"{ws_url}/ws/hub/{self._hub_id}/?token={self._hub_jwt}"

    @property
    def is_configured(self) -> bool:
        """Check if Hub is configured for WebSocket."""
        return bool(self._hub_id and self._hub_jwt)

    def _register_default_handlers(self):
        """Register default command handlers."""
        self.register_handler('install_module', self._handle_install_module)
        self.register_handler('update_module', self._handle_update_module)
        self.register_handler('remove_module', self._handle_remove_module)
        self.register_handler('sync_config', self._handle_sync_config)
        self.register_handler('user_revoked', self._handle_user_revoked)
        self.register_handler('backup_request', self._handle_backup_request)

    def register_handler(self, message_type: str, handler: Callable):
        """Register a message handler."""
        self._handlers[message_type] = handler
        logger.debug(f"[WS] Registered handler for {message_type}")

    def start(self):
        """Start WebSocket client in background thread."""
        if self._running:
            logger.warning("[WS] Client already running")
            return

        self._load_config()

        if not self.is_configured:
            logger.warning("[WS] Hub not configured, client not started")
            return

        self._running = True

        # Start connection thread
        self._thread = threading.Thread(
            target=self._connection_loop,
            daemon=True,
            name="WebSocketClient"
        )
        self._thread.start()

        logger.info("[WS] Client started")

    def stop(self):
        """Stop WebSocket client."""
        if not self._running:
            return

        self._running = False

        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

        logger.info("[WS] Client stopped")

    def send(self, message_type: str, data: Dict = None):
        """
        Send message to Cloud.

        Args:
            message_type: Type of message (heartbeat, user_sync, etc.)
            data: Message payload
        """
        if not self.ws:
            logger.warning("[WS] Cannot send - not connected")
            return

        message = {
            'type': message_type,
            **(data or {})
        }

        try:
            self.ws.send(json.dumps(message))
            logger.debug(f"[WS] Sent: {message_type}")
        except Exception as e:
            logger.error(f"[WS] Send error: {e}")

    def _connection_loop(self):
        """Main connection loop with auto-reconnect."""
        import websocket

        while self._running:
            try:
                logger.info(f"[WS] Connecting to Cloud...")

                self.ws = websocket.WebSocketApp(
                    self._cloud_ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close
                )

                # Run WebSocket (blocking)
                self.ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10
                )

            except Exception as e:
                logger.error(f"[WS] Connection error: {e}")

            if self._running:
                # Reconnect with exponential backoff
                logger.info(f"[WS] Reconnecting in {self._reconnect_delay}s...")
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2,
                    self.MAX_RECONNECT_DELAY
                )

    def _on_open(self, ws):
        """Handle WebSocket connection opened."""
        logger.info("[WS] Connected to Cloud")
        self._reconnect_delay = self.RECONNECT_DELAY

        # Start heartbeat thread
        self._start_heartbeat()

    def _on_message(self, ws, message):
        """Handle message received from Cloud."""
        try:
            data = json.loads(message)
            message_type = data.get('type')

            logger.debug(f"[WS] Received: {message_type}")

            # Find and call handler
            handler = self._handlers.get(message_type)
            if handler:
                try:
                    handler(data)
                except Exception as e:
                    logger.error(f"[WS] Handler error for {message_type}: {e}")
            else:
                logger.debug(f"[WS] No handler for: {message_type}")

        except json.JSONDecodeError:
            logger.error("[WS] Invalid JSON received")
        except Exception as e:
            logger.error(f"[WS] Error processing message: {e}")

    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        logger.error(f"[WS] Error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection closed."""
        logger.info(f"[WS] Disconnected (code={close_status_code})")
        self._stop_heartbeat()

    def _start_heartbeat(self):
        """Start heartbeat thread."""
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="WebSocketHeartbeat"
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        """Stop heartbeat thread."""
        # Thread will stop on next iteration when ws is None
        pass

    def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while self._running and self.ws:
            try:
                self.send('heartbeat', {
                    'version': getattr(settings, 'HUB_VERSION', '1.0.0'),
                    'status': 'healthy'
                })
            except Exception as e:
                logger.error(f"[WS] Heartbeat error: {e}")
                break

            # Sleep in small intervals for quick shutdown
            for _ in range(self.HEARTBEAT_INTERVAL):
                if not self._running or not self.ws:
                    break
                time.sleep(1)

    # ==========================================================================
    # Default Command Handlers
    # ==========================================================================

    def _handle_install_module(self, data: Dict):
        """Handle install_module command from Cloud."""
        module_id = data.get('module_id')
        version = data.get('version')
        logger.info(f"[WS] Command: Install module {module_id} v{version}")
        # TODO: Implement module installation

    def _handle_update_module(self, data: Dict):
        """Handle update_module command from Cloud."""
        module_id = data.get('module_id')
        version = data.get('version')
        logger.info(f"[WS] Command: Update module {module_id} to v{version}")
        # TODO: Implement module update

    def _handle_remove_module(self, data: Dict):
        """Handle remove_module command from Cloud."""
        module_id = data.get('module_id')
        logger.info(f"[WS] Command: Remove module {module_id}")
        # TODO: Implement module removal

    def _handle_sync_config(self, data: Dict):
        """Handle sync_config command from Cloud."""
        logger.info("[WS] Command: Sync config")
        # TODO: Implement config sync

    def _handle_user_revoked(self, data: Dict):
        """Handle user_revoked notification from Cloud."""
        user_id = data.get('user_id')
        logger.info(f"[WS] Notification: User {user_id} access revoked")
        # TODO: Implement user session termination

    def _handle_backup_request(self, data: Dict):
        """Handle backup_request command from Cloud."""
        request_id = data.get('request_id')
        logger.info(f"[WS] Command: Backup request {request_id}")
        # TODO: Implement backup creation


# =============================================================================
# Global instance and helpers
# =============================================================================

_websocket_client: Optional[WebSocketClient] = None


def get_websocket_client() -> WebSocketClient:
    """Get or create WebSocketClient instance."""
    global _websocket_client
    if _websocket_client is None:
        _websocket_client = WebSocketClient()
    return _websocket_client


def start_websocket_client():
    """Start the WebSocket client (call from AppConfig.ready())."""
    client = get_websocket_client()
    client.start()


def stop_websocket_client():
    """Stop the WebSocket client."""
    global _websocket_client
    if _websocket_client:
        _websocket_client.stop()
        _websocket_client = None
