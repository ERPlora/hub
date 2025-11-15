#!/usr/bin/env python
"""
Test FRP tunnel connection with registered hub credentials.
"""
import os
import sys
import django
import time
import requests

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Updated to use multi_device plugin
# Note: This test should be run after plugin is installed and active
try:
    from multi_device.frp_client import get_frp_client, FRPClientError
except ImportError:
    # Fallback for backward compatibility during migration
    from apps.core.frp_client import get_frp_client, FRPClientError

def test_frp_tunnel():
    """Test FRP tunnel connection."""
    print("=" * 60)
    print("Testing FRP Tunnel Connection")
    print("=" * 60)

    try:
        # Get FRP client (will use HubConfig)
        client = get_frp_client()

        print(f"\n✅ FRP Client initialized:")
        print(f"   Hub ID: {client.hub_id}")
        print(f"   Tunnel Port: {client.tunnel_port}")
        print(f"   Server: {client.server_addr}:{client.server_port}")
        print(f"   Local Port: {client.local_port}")

        # Stop if already running (cleanup)
        if client.is_running():
            print("\n⚠️  FRP client is already running, stopping...")
            client.stop()
            time.sleep(2)

        # Start FRP client
        print("\n🚀 Starting FRP client...")
        client.start()

        # Wait for connection
        print("⏳ Waiting for FRP connection to establish...")
        time.sleep(5)

        # Check status
        if client.is_running():
            print("✅ FRP client is running")

            # Test tunnel connection
            print(f"\n🔗 Testing tunnel connection at localhost:{client.tunnel_port}...")
            try:
                response = requests.get(f'http://localhost:{client.tunnel_port}/', timeout=5)
                print(f"✅ Tunnel is working! Status code: {response.status_code}")
                print(f"   Response preview: {response.text[:100]}...")
            except requests.exceptions.RequestException as e:
                print(f"❌ Tunnel test failed: {e}")
        else:
            print("❌ FRP client failed to start")

        print("\n" + "=" * 60)
        print("Keep the FRP client running to test the tunnel.")
        print("Press Ctrl+C to stop the FRP client.")
        print("=" * 60)

        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n⏸️  Stopping FRP client...")
            client.stop()
            print("✅ FRP client stopped")

    except FRPClientError as e:
        print(f"\n❌ FRP Client Error: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    test_frp_tunnel()
