#!/usr/bin/env python
"""
Configure Hub with credentials obtained from registration API.

This script sets up HubConfig with the credentials returned from
the successful hub registration test.
"""
import os
import sys
import django
import uuid

# Setup Django
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import HubConfig

def configure_hub():
    """Configure Hub with registration credentials."""
    # Credentials from successful registration
    hub_id = uuid.UUID('4aa5a11c-b9be-4e21-afb6-37adc2b7b1ff')
    tunnel_port = 7101
    tunnel_token = 'NecIo2tuRhgbQr3ABE6_ThF41nEO8-f0_UD0X1760f4'

    # Get or create config
    config = HubConfig.get_config()

    # Update with registration data
    config.hub_id = hub_id
    config.tunnel_port = tunnel_port
    config.tunnel_token = tunnel_token
    config.is_configured = True
    config.save()

    print("✅ Hub configured successfully:")
    print(f"   Hub ID: {config.hub_id}")
    print(f"   Tunnel Port: {config.tunnel_port}")
    print(f"   Tunnel Token: {config.tunnel_token[:20]}...")
    print(f"   Is Configured: {config.is_configured}")

    return config

if __name__ == '__main__':
    configure_hub()
