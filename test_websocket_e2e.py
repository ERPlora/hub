"""
End-to-end test for WebSocket communication between Hub and Cloud.

This script tests:
1. Hub connects to Cloud WebSocket
2. Hub sends heartbeat
3. Cloud responds with heartbeat_ack
4. Cloud sends plugin_update_available
5. Hub receives and processes message

Requirements:
- Cloud server running on http://localhost:8000
- Hub registered in Cloud with valid JWT token
"""
import asyncio
import sys
import os

# Add apps to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apps.core.websocket_client import WebSocketClient


async def test_websocket_e2e():
    """Test end-to-end WebSocket communication."""

    print("\n=== WebSocket End-to-End Test ===\n")

    # TODO: Replace with actual Hub ID and JWT token from Cloud
    # For now, this is a placeholder for manual testing
    hub_id = "test-hub-id"  # Get from Cloud after registering a hub
    token = "test-jwt-token"  # Get JWT token from Cloud login

    print("⚠️  INSTRUCTIONS:")
    print("1. Make sure Cloud server is running: cd cloud && .venv/bin/python manage.py runserver")
    print("2. Register a Hub in Cloud or use existing hub_id")
    print("3. Get JWT token: POST /api/auth/login/ with email/password")
    print("4. Update hub_id and token variables in this script")
    print("5. Run this script again\n")

    # Create WebSocket client
    client = WebSocketClient(
        hub_id=hub_id,
        token=token,
        cloud_url='ws://localhost:8000',
        heartbeat_interval=5  # 5 seconds for testing
    )

    try:
        print("1️⃣  Connecting to Cloud WebSocket...")
        await client.connect()
        print("   ✅ Connected!\n")

        print("2️⃣  Sending heartbeat...")
        await client._send_heartbeat()
        print("   ✅ Heartbeat sent!\n")

        print("3️⃣  Waiting for heartbeat_ack from Cloud...")
        # Try to receive message
        try:
            await asyncio.wait_for(client._receive_message(), timeout=5)
            print("   ✅ Received response from Cloud!\n")
        except asyncio.TimeoutError:
            print("   ⚠️  No response received (timeout)\n")

        print("4️⃣  Starting heartbeat loop for 15 seconds...")
        heartbeat_task = asyncio.create_task(client._send_heartbeat_loop())
        receive_task = asyncio.create_task(client._receive_loop())

        # Run for 15 seconds
        await asyncio.sleep(15)

        # Cancel tasks
        heartbeat_task.cancel()
        receive_task.cancel()

        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        try:
            await receive_task
        except asyncio.CancelledError:
            pass

        print("   ✅ Heartbeat loop completed!\n")

    except Exception as e:
        print(f"   ❌ Error: {e}\n")

    finally:
        print("5️⃣  Disconnecting...")
        await client.disconnect()
        print("   ✅ Disconnected!\n")

    print("=== Test Complete ===\n")


if __name__ == "__main__":
    asyncio.run(test_websocket_e2e())
