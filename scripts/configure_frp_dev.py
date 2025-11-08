#!/usr/bin/env python
"""
Configure Hub for FRP development testing.

Creates a HubConfig with test credentials so FRP client can connect.
"""
import os
import sys
import django
import uuid

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import HubConfig

def main():
    print("🔧 Configuring Hub for FRP development testing...\n")

    # Get or create config
    config = HubConfig.get_config()

    # Set development credentials
    config.hub_id = uuid.uuid4()
    config.tunnel_port = 7101  # First available port in range
    config.tunnel_token = "cpos-local-dev-token"  # Same as FRP server
    config.is_configured = True
    config.save()

    print(f"✅ Hub configured successfully!\n")
    print(f"   Hub ID: {config.hub_id}")
    print(f"   Tunnel Port: {config.tunnel_port}")
    print(f"   Tunnel Token: {config.tunnel_token}")
    print(f"   Is Configured: {config.is_configured}\n")
    print("📡 FRP client will connect to: localhost:7100")
    print("🌐 Hub will be accessible via tunnel on: localhost:7101\n")
    print("You can now start the Hub and test FRP connection!")

if __name__ == '__main__':
    main()
