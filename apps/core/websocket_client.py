"""
WebSocket Client for Hub real-time communication with Cloud.

Handles:
- WebSocket connection to Cloud
- Heartbeat sending every 30 seconds
- Automatic reconnection on disconnect
- Message handling from Cloud (plugin updates, user revocations, backup requests)
"""
import asyncio
import json
import logging
import websockets
from typing import Optional, Callable
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WebSocketClientError(Exception):
    """Exception raised for WebSocket client errors."""
    pass


class WebSocketClient:
    """
    WebSocket client for Hub→Cloud communication.

    Protocol:
    - Connection URL: ws://localhost:8000/ws/hub/{hub_id}/?token={jwt_token}
    - Messages Hub→Cloud: heartbeat, user_sync, plugin_installed
    - Messages Cloud→Hub: plugin_update_available, user_revoked, backup_request
    """

    def __init__(
        self,
        hub_id: str,
        token: str,
        cloud_url: str = 'ws://localhost:8000',
        heartbeat_interval: int = 30,
        reconnect_delay: int = 5,
        max_reconnect_attempts: int = 10
    ):
        """
        Initialize WebSocket client.

        Args:
            hub_id: Hub UUID
            token: JWT access token
            cloud_url: Cloud WebSocket URL
            heartbeat_interval: Seconds between heartbeats (default: 30)
            reconnect_delay: Seconds to wait before reconnecting (default: 5)
            max_reconnect_attempts: Max reconnection attempts (default: 10)
        """
        self.hub_id = hub_id
        self.token = token
        self.cloud_url = cloud_url
        self.heartbeat_interval = heartbeat_interval
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts

        # WebSocket connection
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False

        # Tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None

        # Message handlers
        self._message_handlers = {
            'heartbeat_ack': self._handle_heartbeat_ack,
            'plugin_update_available': self._handle_plugin_update,
            'user_revoked': self._handle_user_revoked,
            'backup_request': self._handle_backup_request,
        }

    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self.ws is not None

    async def connect(self):
        """
        Connect to Cloud WebSocket server.

        Raises:
            WebSocketClientError: If connection fails
        """
        try:
            # Build WebSocket URL with hub_id and token
            ws_url = f"{self.cloud_url}/ws/hub/{self.hub_id}/?token={self.token}"

            logger.info(f"Connecting to Cloud WebSocket: {ws_url}")

            # Connect to WebSocket
            self.ws = await websockets.connect(ws_url)
            self._connected = True

            logger.info(f"Hub {self.hub_id}: WebSocket connected")

        except Exception as e:
            logger.error(f"Hub {self.hub_id}: WebSocket connection failed: {e}")
            self._connected = False
            raise WebSocketClientError(f"Failed to connect: {e}")

    async def disconnect(self):
        """Disconnect from Cloud WebSocket server."""
        if not self.is_connected():
            return

        try:
            # Cancel tasks
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

            if self._receive_task and not self._receive_task.done():
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass

            # Close WebSocket
            if self.ws:
                await self.ws.close()

            self._connected = False
            logger.info(f"Hub {self.hub_id}: WebSocket disconnected")

        except Exception as e:
            logger.error(f"Hub {self.hub_id}: Error during disconnect: {e}")

    async def start(self):
        """
        Start WebSocket client (connect + start tasks).

        This method starts the heartbeat and message receive loops.
        """
        await self.connect()

        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._send_heartbeat_loop())

        # Start receive task
        self._receive_task = asyncio.create_task(self._receive_loop())

        logger.info(f"Hub {self.hub_id}: WebSocket client started")

    async def stop(self):
        """Stop WebSocket client."""
        await self.disconnect()
        logger.info(f"Hub {self.hub_id}: WebSocket client stopped")

    # Heartbeat methods

    async def _send_heartbeat_loop(self):
        """Send heartbeat to Cloud every heartbeat_interval seconds."""
        try:
            while self.is_connected():
                await self._send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
        except asyncio.CancelledError:
            logger.debug(f"Hub {self.hub_id}: Heartbeat loop cancelled")
        except Exception as e:
            logger.exception(f"Hub {self.hub_id}: Error in heartbeat loop: {e}")

    async def _send_heartbeat(self):
        """Send single heartbeat message."""
        if not self.is_connected():
            return

        try:
            message = {
                'type': 'heartbeat',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            await self.ws.send(json.dumps(message))
            logger.debug(f"Hub {self.hub_id}: Heartbeat sent")

        except Exception as e:
            logger.error(f"Hub {self.hub_id}: Error sending heartbeat: {e}")

    # Receive methods

    async def _receive_loop(self):
        """Receive messages from Cloud in a loop."""
        try:
            while self.is_connected():
                await self._receive_message()
        except asyncio.CancelledError:
            logger.debug(f"Hub {self.hub_id}: Receive loop cancelled")
        except Exception as e:
            logger.exception(f"Hub {self.hub_id}: Error in receive loop: {e}")

    async def _receive_message(self):
        """Receive and process a single message from Cloud."""
        if not self.is_connected():
            return

        try:
            # Receive message
            message_str = await self.ws.recv()
            message = json.loads(message_str)

            message_type = message.get('type')
            logger.debug(f"Hub {self.hub_id}: Received message type: {message_type}")

            # Handle message
            handler = self._message_handlers.get(message_type)
            if handler:
                await handler(message)
            else:
                logger.debug(f"Hub {self.hub_id}: Unknown message type: {message_type}")

        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"Hub {self.hub_id}: WebSocket connection closed")
            self._connected = False
        except json.JSONDecodeError as e:
            logger.error(f"Hub {self.hub_id}: Invalid JSON received: {e}")
        except Exception as e:
            logger.exception(f"Hub {self.hub_id}: Error receiving message: {e}")

    # Message handlers

    async def _handle_heartbeat_ack(self, message: dict):
        """Handle heartbeat acknowledgement from Cloud."""
        logger.debug(f"Hub {self.hub_id}: Heartbeat ACK received")

    async def _handle_plugin_update(self, message: dict):
        """Handle plugin update notification from Cloud."""
        plugin_id = message.get('plugin_id')
        version = message.get('version')
        logger.info(f"Hub {self.hub_id}: Plugin update available: {plugin_id} v{version}")

        # TODO: Trigger plugin update check
        # from apps.plugins.manager import get_plugin_manager
        # manager = get_plugin_manager()
        # await manager.check_update(plugin_id, version)

    async def _handle_user_revoked(self, message: dict):
        """Handle user revocation notification from Cloud."""
        user_id = message.get('user_id')
        logger.warning(f"Hub {self.hub_id}: User revoked: {user_id}")

        # TODO: Revoke user access locally
        # from apps.users.manager import get_user_manager
        # manager = get_user_manager()
        # await manager.revoke_user(user_id)

    async def _handle_backup_request(self, message: dict):
        """Handle backup request from Cloud."""
        request_id = message.get('request_id')
        logger.info(f"Hub {self.hub_id}: Backup requested (request_id: {request_id})")

        # TODO: Trigger backup creation
        # from apps.core.backup import get_backup_service
        # service = get_backup_service()
        # await service.create_and_upload_backup(request_id)

    # Public send methods

    async def send_user_sync(self, user_data: dict):
        """Send user synchronization data to Cloud."""
        if not self.is_connected():
            logger.warning(f"Hub {self.hub_id}: Cannot send user_sync, not connected")
            return

        try:
            message = {
                'type': 'user_sync',
                'data': user_data
            }

            await self.ws.send(json.dumps(message))
            logger.info(f"Hub {self.hub_id}: User sync sent")

        except Exception as e:
            logger.error(f"Hub {self.hub_id}: Error sending user_sync: {e}")

    async def send_plugin_installed(self, plugin_id: str, version: str):
        """Notify Cloud about plugin installation."""
        if not self.is_connected():
            logger.warning(f"Hub {self.hub_id}: Cannot send plugin_installed, not connected")
            return

        try:
            message = {
                'type': 'plugin_installed',
                'plugin_id': plugin_id,
                'version': version
            }

            await self.ws.send(json.dumps(message))
            logger.info(f"Hub {self.hub_id}: Plugin installed notification sent: {plugin_id}")

        except Exception as e:
            logger.error(f"Hub {self.hub_id}: Error sending plugin_installed: {e}")


# Global WebSocket client instance
_websocket_client: Optional[WebSocketClient] = None


def get_websocket_client() -> Optional[WebSocketClient]:
    """Get global WebSocket client instance."""
    return _websocket_client


def set_websocket_client(client: WebSocketClient):
    """Set global WebSocket client instance."""
    global _websocket_client
    _websocket_client = client
