"""
Tests for WebSocket Client (TDD).

Test coverage:
- WebSocket connection to Cloud
- Heartbeat sending every 30s
- Reconnection on disconnect
- Message handling from Cloud
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from apps.core.websocket_client import WebSocketClient, WebSocketClientError


pytestmark = pytest.mark.unit


class TestWebSocketClientConnection:
    """Test WebSocket client connection."""

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_connect_success(self, mock_connect):
        """
        GIVEN: Valid Hub configuration with JWT token
        WHEN: WebSocket client connects
        THEN: Connection should be established
        """
        # Mock WebSocket connection
        mock_ws = AsyncMock()
        mock_connect.return_value = mock_ws

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000'
        )

        await client.connect()

        # Should have called websockets.connect
        mock_connect.assert_called_once()
        assert client.is_connected() is True

        await client.disconnect()

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_connect_with_invalid_token_raises_error(self, mock_connect):
        """
        GIVEN: Invalid JWT token
        WHEN: WebSocket client tries to connect
        THEN: Should raise WebSocketClientError
        """
        # Mock connection failure
        mock_connect.side_effect = Exception("Connection refused")

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='invalid-token',
            cloud_url='ws://localhost:8000'
        )

        with pytest.raises(WebSocketClientError):
            await client.connect()

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_disconnect_closes_connection(self, mock_connect):
        """
        GIVEN: Connected WebSocket client
        WHEN: disconnect() is called
        THEN: Connection should be closed
        """
        mock_ws = AsyncMock()
        mock_connect.return_value = mock_ws

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000'
        )

        await client.connect()
        await client.disconnect()

        # Should close WebSocket
        mock_ws.close.assert_called_once()
        assert client.is_connected() is False


class TestHeartbeatSending:
    """Test heartbeat message sending."""

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_heartbeat_sent_periodically(self, mock_connect):
        """
        GIVEN: Connected WebSocket client
        WHEN: Client is running
        THEN: Heartbeat should be sent every 30 seconds
        """
        mock_ws = AsyncMock()
        mock_connect.return_value = mock_ws

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000',
            heartbeat_interval=1  # 1 second for testing
        )

        await client.connect()

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(client._send_heartbeat_loop())

        # Wait for at least 2 heartbeats
        await asyncio.sleep(2.5)

        # Cancel task
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        # Should have sent at least 2 heartbeats
        assert mock_ws.send.call_count >= 2

        await client.disconnect()

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_heartbeat_ack_received(self, mock_connect):
        """
        GIVEN: Connected WebSocket client that sends heartbeat
        WHEN: Server responds with heartbeat_ack
        THEN: Client should process the ack
        """
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = '{"type": "heartbeat_ack", "timestamp": "2025-01-08T00:00:00Z"}'
        mock_connect.return_value = mock_ws

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000'
        )

        await client.connect()

        # Process one message
        await client._receive_message()

        # Should have received heartbeat_ack
        # (implementation will log this)

        await client.disconnect()


class TestReconnection:
    """Test automatic reconnection."""

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_reconnect_on_connection_loss(self, mock_connect):
        """
        GIVEN: Connected WebSocket client
        WHEN: Connection is lost
        THEN: Client should attempt to reconnect
        """
        # First connection succeeds, second fails, third succeeds
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        mock_connect.side_effect = [
            mock_ws1,  # First connection
            Exception("Connection lost"),  # Reconnect fails
            mock_ws2,  # Reconnect succeeds
        ]

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000',
            reconnect_delay=0.1  # Fast reconnect for testing
        )

        await client.connect()
        assert client.is_connected() is True

        # Simulate connection loss
        await client.disconnect()
        assert client.is_connected() is False

        # Try reconnect (will fail once)
        try:
            await client.connect()
        except WebSocketClientError:
            pass

        # Try reconnect again (should succeed)
        await client.connect()
        assert client.is_connected() is True

        await client.disconnect()


class TestMessageHandling:
    """Test handling messages from Cloud."""

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_plugin_update_notification_handled(self, mock_connect):
        """
        GIVEN: Connected WebSocket client
        WHEN: Cloud sends plugin_update_available message
        THEN: Client should handle it
        """
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = '{"type": "plugin_update_available", "plugin_id": "test-plugin", "version": "1.0.1"}'
        mock_connect.return_value = mock_ws

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000'
        )

        await client.connect()

        # Process message
        await client._receive_message()

        # Should have processed plugin update
        # (implementation will handle this)

        await client.disconnect()

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_user_revoked_notification_handled(self, mock_connect):
        """
        GIVEN: Connected WebSocket client
        WHEN: Cloud sends user_revoked message
        THEN: Client should handle it
        """
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = '{"type": "user_revoked", "user_id": "123"}'
        mock_connect.return_value = mock_ws

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000'
        )

        await client.connect()

        # Process message
        await client._receive_message()

        # Should have processed user revocation
        # (implementation will handle this)

        await client.disconnect()

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_backup_request_handled(self, mock_connect):
        """
        GIVEN: Connected WebSocket client
        WHEN: Cloud sends backup_request message
        THEN: Client should handle it
        """
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = '{"type": "backup_request", "request_id": "req-123"}'
        mock_connect.return_value = mock_ws

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000'
        )

        await client.connect()

        # Process message
        await client._receive_message()

        # Should have processed backup request
        # (implementation will handle this)

        await client.disconnect()

    @patch('apps.core.websocket_client.websockets.connect', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_unknown_message_ignored(self, mock_connect):
        """
        GIVEN: Connected WebSocket client
        WHEN: Cloud sends unknown message type
        THEN: Client should ignore it gracefully
        """
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = '{"type": "unknown_type", "data": "test"}'
        mock_connect.return_value = mock_ws

        client = WebSocketClient(
            hub_id='test-hub-id',
            token='test-token',
            cloud_url='ws://localhost:8000'
        )

        await client.connect()

        # Should not crash
        await client._receive_message()

        await client.disconnect()
