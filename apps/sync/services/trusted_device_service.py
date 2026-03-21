"""
Trusted Device Service — calls Cloud API to manage trusted devices.

Replaces the local TrustedDevice model. All trust state is stored in Cloud.
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class TrustedDeviceService:
    """Service for managing trusted devices via Cloud API."""

    DEFAULT_TIMEOUT = 10

    def __init__(self):
        self.base_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')

    def verify(self, device_token):
        """
        Verify a device token against Cloud.

        Returns:
            dict with 'valid', 'user_email', 'device' if valid
            dict with 'valid': False if invalid
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/trusted-devices/verify/",
                json={'device_token': device_token},
                timeout=self.DEFAULT_TIMEOUT,
            )

            if response.status_code == 200:
                return response.json()

            return {'valid': False}

        except requests.exceptions.RequestException as e:
            logger.warning(f"[TRUSTED DEVICE] Verify failed: {e}")
            return {'valid': False}

    def create(self, access_token, user_agent='', ip_address=None):
        """
        Create a trusted device in Cloud for the authenticated user.

        Args:
            access_token: User's Cloud JWT access token
            user_agent: Browser user agent string
            ip_address: Client IP address

        Returns:
            dict with 'device_token' and 'device' on success, None on failure
        """
        try:
            data = {'user_agent': user_agent}
            if ip_address:
                data['ip_address'] = ip_address

            response = requests.post(
                f"{self.base_url}/api/auth/trusted-devices/create/",
                json=data,
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=self.DEFAULT_TIMEOUT,
            )

            if response.status_code == 201:
                return response.json()

            logger.warning(f"[TRUSTED DEVICE] Create failed: {response.status_code}")
            return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"[TRUSTED DEVICE] Create failed: {e}")
            return None

    def list_devices(self, access_token):
        """
        List trusted devices for the authenticated user.

        Args:
            access_token: User's Cloud JWT access token

        Returns:
            list of device dicts, or empty list on failure
        """
        try:
            response = requests.get(
                f"{self.base_url}/api/auth/trusted-devices/",
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=self.DEFAULT_TIMEOUT,
            )

            if response.status_code == 200:
                return response.json()

            return []

        except requests.exceptions.RequestException as e:
            logger.warning(f"[TRUSTED DEVICE] List failed: {e}")
            return []

    def revoke(self, access_token, device_id):
        """
        Revoke a trusted device.

        Args:
            access_token: User's Cloud JWT access token
            device_id: Device ID to revoke

        Returns:
            True if revoked, False on failure
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/trusted-devices/{device_id}/revoke/",
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=self.DEFAULT_TIMEOUT,
            )

            return response.status_code == 200

        except requests.exceptions.RequestException as e:
            logger.warning(f"[TRUSTED DEVICE] Revoke failed: {e}")
            return False
