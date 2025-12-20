"""
Marketplace Client for Hub-to-Cloud plugin API communication.

Uses hub_jwt (RS256, 1 year validity) for authentication via X-Hub-Token header.
"""
import requests
import logging
from typing import Optional
from django.conf import settings

from apps.configuration.models import HubConfig

logger = logging.getLogger(__name__)


class MarketplaceError(Exception):
    """Base exception for marketplace errors"""
    pass


class MarketplaceAuthError(MarketplaceError):
    """Authentication error (invalid or expired hub_jwt)"""
    pass


class MarketplaceConnectionError(MarketplaceError):
    """Connection error (Cloud unreachable)"""
    pass


class MarketplaceClient:
    """
    Client for Cloud Plugin Marketplace API.

    Authenticates using hub_jwt stored in HubConfig.
    All API calls use X-Hub-Token header.

    Usage:
        client = MarketplaceClient()

        # List plugins
        plugins = client.list_plugins(category='sales')

        # Get plugin detail
        plugin = client.get_plugin('plugin-uuid')

        # Download plugin
        zip_content = client.download_plugin('plugin-uuid')

        # Check ownership
        owned = client.check_ownership('plugin-uuid')
    """

    DEFAULT_TIMEOUT = 30

    def __init__(self):
        self.hub_config = HubConfig.get_config()
        self.base_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')

    def _get_headers(self) -> dict:
        """Get headers with hub_jwt authentication"""
        if not self.hub_config.hub_jwt:
            raise MarketplaceAuthError(
                "Hub not configured. Please login with Cloud account first."
            )

        return {
            'X-Hub-Token': self.hub_config.hub_jwt,
            'Content-Type': 'application/json',
        }

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        timeout: int = DEFAULT_TIMEOUT,
        stream: bool = False
    ) -> requests.Response:
        """
        Make authenticated request to marketplace API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., 'plugins/', 'plugins/{id}/download/')
            params: Query parameters
            json_data: JSON body for POST/PUT
            timeout: Request timeout in seconds
            stream: Whether to stream the response (for downloads)

        Returns:
            Response object

        Raises:
            MarketplaceAuthError: If authentication fails
            MarketplaceConnectionError: If Cloud is unreachable
            MarketplaceError: For other API errors
        """
        url = f"{self.base_url}/api/marketplace/{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self._get_headers(),
                params=params,
                json=json_data,
                timeout=timeout,
                stream=stream
            )

            if response.status_code == 401:
                raise MarketplaceAuthError(
                    "Hub authentication failed. Token may be expired. "
                    "Please login again with Cloud account."
                )

            if response.status_code == 403:
                raise MarketplaceAuthError(
                    "Access denied. You don't have permission to access this resource."
                )

            return response

        except requests.exceptions.ConnectionError:
            raise MarketplaceConnectionError(
                "Cannot connect to Cloud. Check your internet connection."
            )
        except requests.exceptions.Timeout:
            raise MarketplaceConnectionError(
                f"Connection timeout after {timeout}s. Cloud may be slow or unreachable."
            )

    def is_configured(self) -> bool:
        """Check if Hub has valid marketplace credentials"""
        return bool(self.hub_config.hub_jwt and self.hub_config.hub_id)

    # =========================================================================
    # Plugin Listing
    # =========================================================================

    def list_plugins(
        self,
        category: Optional[str] = None,
        plugin_type: Optional[str] = None,
        search: Optional[str] = None,
        ordering: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> dict:
        """
        List plugins from marketplace.

        Args:
            category: Filter by category (e.g., 'sales', 'inventory')
            plugin_type: Filter by type ('free', 'paid', 'subscription')
            search: Search term for name/description
            ordering: Order by field ('-downloads', 'price', etc.)
            page: Page number (1-based)
            page_size: Items per page

        Returns:
            Dict with 'count', 'next', 'previous', 'results' keys
        """
        params = {
            'page': page,
            'page_size': page_size,
        }

        if category:
            params['category'] = category
        if plugin_type:
            params['plugin_type'] = plugin_type
        if search:
            params['search'] = search
        if ordering:
            params['ordering'] = ordering

        response = self._request('GET', 'plugins/', params=params)
        response.raise_for_status()
        return response.json()

    def get_categories(self, language: str = 'en') -> list:
        """
        Get all plugin categories.

        Args:
            language: Language code for category names ('en', 'es', etc.)

        Returns:
            List of category dicts with 'id', 'name', 'description'
        """
        response = self._request('GET', 'categories/', params={'language': language})
        response.raise_for_status()
        return response.json()

    def get_featured(self) -> list:
        """
        Get featured plugins.

        Returns:
            List of plugin dicts (max 10)
        """
        response = self._request('GET', 'plugins/featured/')
        response.raise_for_status()
        return response.json()

    def get_my_plugins(self, page: int = 1, page_size: int = 20) -> dict:
        """
        Get plugins owned by Hub owner (purchased + free).

        Returns:
            Dict with 'count', 'next', 'previous', 'results' keys
        """
        params = {'page': page, 'page_size': page_size}
        response = self._request('GET', 'plugins/my_plugins/', params=params)
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Plugin Detail
    # =========================================================================

    def get_plugin(self, plugin_id: str) -> dict:
        """
        Get plugin detail.

        Args:
            plugin_id: Plugin UUID

        Returns:
            Plugin dict with full details
        """
        response = self._request('GET', f'plugins/{plugin_id}/')
        response.raise_for_status()
        return response.json()

    def check_ownership(self, plugin_id: str) -> dict:
        """
        Check if Hub owner owns this plugin.

        Args:
            plugin_id: Plugin UUID

        Returns:
            Dict with 'owned', 'purchase_type', 'purchase_id', 'purchased_at'
        """
        response = self._request('GET', f'plugins/{plugin_id}/check_ownership/')
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Download & Install
    # =========================================================================

    def download_plugin(self, plugin_id: str) -> bytes:
        """
        Download plugin ZIP file.

        Only works for free plugins or plugins owned by Hub owner.
        Rate limited to 10 downloads per hour.

        Args:
            plugin_id: Plugin UUID

        Returns:
            ZIP file content as bytes

        Raises:
            MarketplaceAuthError: If not authorized to download
            MarketplaceError: If download fails
        """
        response = self._request(
            'GET',
            f'plugins/{plugin_id}/download/',
            timeout=60,
            stream=True
        )

        if response.status_code == 404:
            raise MarketplaceError("Plugin file not available")

        if response.status_code == 429:
            raise MarketplaceError(
                "Download rate limit exceeded. Please wait before downloading again."
            )

        response.raise_for_status()

        # Read full content for ZIP
        return response.content

    def mark_installed(self, plugin_id: str, version: Optional[str] = None) -> dict:
        """
        Mark plugin as installed on this Hub (for Cloud tracking).

        Args:
            plugin_id: Plugin UUID
            version: Installed version (defaults to latest)

        Returns:
            Installation record dict
        """
        json_data = {}
        if version:
            json_data['version'] = version

        response = self._request(
            'POST',
            f'plugins/{plugin_id}/mark_installed/',
            json_data=json_data
        )
        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Purchase
    # =========================================================================

    def initiate_purchase(
        self,
        plugin_id: str,
        success_url: str,
        cancel_url: str
    ) -> dict:
        """
        Initiate plugin purchase (creates Stripe Checkout session).

        For free plugins, this completes immediately.
        For paid plugins, returns Stripe checkout URL.

        Args:
            plugin_id: Plugin UUID
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect if payment cancelled

        Returns:
            For free: {'message': '...', 'is_free': True, 'purchase_id': ...}
            For paid: {'checkout_url': '...', 'session_id': '...', 'mode': '...'}
        """
        response = self._request(
            'POST',
            f'plugins/{plugin_id}/purchase/',
            json_data={
                'success_url': success_url,
                'cancel_url': cancel_url,
            }
        )

        if response.status_code == 409:
            # Already owns the plugin
            data = response.json()
            raise MarketplaceError(data.get('error', 'You already own this plugin'))

        response.raise_for_status()
        return response.json()

    # =========================================================================
    # Hub Installations
    # =========================================================================

    def get_hub_installations(self) -> list:
        """
        Get all plugins installed on this Hub (from Cloud records).

        Returns:
            List of installation dicts
        """
        response = self._request('GET', 'hub-plugins/')
        response.raise_for_status()
        return response.json()
