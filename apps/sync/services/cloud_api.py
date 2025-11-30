"""
Cloud API Service for Hub-to-Cloud communication.

Uses JWT authentication (Arquitectura Unificada Opción A).
All requests are authenticated with hub_jwt token.
"""
import logging
import requests
import jwt
from typing import Optional, Dict, Any, List
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.configuration.models import HubConfig

logger = logging.getLogger(__name__)


class CloudAPIError(Exception):
    """Base exception for Cloud API errors."""
    def __init__(self, message: str, status_code: int = None, response: dict = None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class CloudAPIService:
    """
    Service for Hub-to-Cloud API communication.

    Handles:
    - Heartbeat requests
    - Command polling
    - Plugin marketplace access
    - Configuration sync

    All requests use JWT authentication.
    """

    DEFAULT_TIMEOUT = 10  # seconds

    def __init__(self):
        self.config = HubConfig.get_solo()
        self.base_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
        self.hub_jwt = self.config.hub_jwt
        self.hub_id = str(self.config.hub_id) if self.config.hub_id else None

    @property
    def is_configured(self) -> bool:
        """Check if Hub is configured with Cloud credentials."""
        return bool(self.hub_jwt and self.hub_id)

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with JWT authentication."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        if self.hub_jwt:
            headers['Authorization'] = f'Bearer {self.hub_jwt}'

        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None,
        timeout: int = None
    ) -> Dict[str, Any]:
        """
        Make authenticated request to Cloud API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., '/api/hubs/me/heartbeat/')
            data: Request body (for POST/PUT)
            params: Query parameters
            timeout: Request timeout in seconds

        Returns:
            Response JSON data

        Raises:
            CloudAPIError: On request failure
        """
        if not self.is_configured:
            raise CloudAPIError("Hub not configured with Cloud credentials")

        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.DEFAULT_TIMEOUT

        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=self._get_headers(),
                json=data,
                params=params,
                timeout=timeout
            )

            # Log request
            logger.debug(
                f"[CLOUD API] {method.upper()} {endpoint} -> {response.status_code}"
            )

            # Handle response
            if response.status_code == 401:
                logger.warning("[CLOUD API] Unauthorized - JWT may be expired")
                raise CloudAPIError(
                    "Unauthorized - JWT expired or invalid",
                    status_code=401
                )

            if response.status_code == 403:
                raise CloudAPIError(
                    "Forbidden - Access denied",
                    status_code=403
                )

            if response.status_code >= 400:
                error_data = response.json() if response.content else {}
                raise CloudAPIError(
                    f"API error: {response.status_code}",
                    status_code=response.status_code,
                    response=error_data
                )

            return response.json() if response.content else {}

        except requests.exceptions.Timeout:
            logger.warning(f"[CLOUD API] Timeout on {endpoint}")
            raise CloudAPIError("Request timeout")

        except requests.exceptions.ConnectionError:
            logger.warning(f"[CLOUD API] Connection error on {endpoint}")
            raise CloudAPIError("Connection error - Cloud not reachable")

        except requests.exceptions.RequestException as e:
            logger.error(f"[CLOUD API] Request error: {str(e)}")
            raise CloudAPIError(f"Request error: {str(e)}")

    # =========================================================================
    # Hub Info & Heartbeat
    # =========================================================================

    def send_heartbeat(self, metadata: Dict = None) -> Dict[str, Any]:
        """
        Send heartbeat to Cloud.

        Args:
            metadata: Optional metadata (version, plugins, status)

        Returns:
            Response from Cloud
        """
        data = metadata or {}

        # Add default metadata
        if 'version' not in data:
            data['version'] = getattr(settings, 'HUB_VERSION', '1.0.0')

        return self._request('POST', '/api/hubs/me/heartbeat/', data=data)

    def get_hub_info(self) -> Dict[str, Any]:
        """Get Hub information from Cloud."""
        return self._request('GET', '/api/hubs/me/')

    # =========================================================================
    # Commands
    # =========================================================================

    def get_pending_commands(self) -> List[Dict[str, Any]]:
        """
        Poll for pending commands from Cloud.

        Returns:
            List of pending commands
        """
        response = self._request('GET', '/api/hubs/me/commands/')
        return response.get('commands', [])

    def acknowledge_command(
        self,
        command_id: str,
        status: str = 'completed',
        result: Dict = None,
        error: str = None
    ) -> Dict[str, Any]:
        """
        Acknowledge command execution.

        Args:
            command_id: Command UUID
            status: 'completed' or 'failed'
            result: Result data
            error: Error message if failed

        Returns:
            Response from Cloud
        """
        data = {
            'status': status,
            'result': result or {},
        }

        if error:
            data['error'] = error

        return self._request(
            'POST',
            f'/api/hubs/me/commands/{command_id}/ack/',
            data=data
        )

    # =========================================================================
    # Command JWT Verification
    # =========================================================================

    def verify_command_jwt(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify a command JWT from Cloud.

        Uses cached public key or fetches from Cloud.

        Args:
            token: Command JWT string

        Returns:
            Token payload if valid, None otherwise
        """
        public_key = self._get_public_key()

        if not public_key:
            logger.warning("[CLOUD API] No public key available for JWT verification")
            return None

        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256']
            )

            # Verify it's a command token for this Hub
            if payload.get('type') != 'hub_command':
                logger.warning("[CLOUD API] Invalid token type for command")
                return None

            if payload.get('hub_id') != self.hub_id:
                logger.warning("[CLOUD API] Command JWT hub_id mismatch")
                return None

            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("[CLOUD API] Command JWT expired")
            return None

        except jwt.InvalidTokenError as e:
            logger.warning(f"[CLOUD API] Invalid command JWT: {str(e)}")
            return None

    def _get_public_key(self) -> Optional[str]:
        """
        Get Cloud's public key for JWT verification.

        Returns cached key or fetches from Cloud.
        """
        # Try cached key first
        if self.config.cloud_public_key:
            return self.config.cloud_public_key

        # Fetch from Cloud
        try:
            response = requests.get(
                f"{self.base_url}/api/auth/public-key/",
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                public_key = data.get('public_key')

                if public_key:
                    # Cache the key
                    HubConfig.set_value('cloud_public_key', public_key)
                    self.config.cloud_public_key = public_key
                    logger.info("[CLOUD API] Cached Cloud public key")
                    return public_key

        except requests.exceptions.RequestException as e:
            logger.warning(f"[CLOUD API] Failed to fetch public key: {str(e)}")

        return None

    # =========================================================================
    # Plugin Marketplace
    # =========================================================================

    def get_marketplace_plugins(self) -> List[Dict[str, Any]]:
        """Get available plugins from marketplace."""
        response = self._request('GET', '/api/plugins/')
        return response.get('plugins', [])

    def download_plugin(self, plugin_id: str, version: str = None) -> Dict[str, Any]:
        """
        Request plugin download URL.

        Args:
            plugin_id: Plugin identifier
            version: Specific version (optional)

        Returns:
            Response with download URL and metadata
        """
        data = {'plugin_id': plugin_id}
        if version:
            data['version'] = version

        return self._request('POST', '/api/plugins/download/', data=data)


# Singleton instance for convenience
_cloud_api_instance = None


def get_cloud_api() -> CloudAPIService:
    """Get or create CloudAPIService instance."""
    global _cloud_api_instance
    if _cloud_api_instance is None:
        _cloud_api_instance = CloudAPIService()
    return _cloud_api_instance
