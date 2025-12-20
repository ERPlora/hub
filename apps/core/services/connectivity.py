"""
Connectivity Checker Service.

Checks if Cloud is reachable (online vs offline mode).
"""
import logging
import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)


class ConnectivityChecker:
    """
    Checks connectivity to Cloud.

    Results are cached briefly to avoid excessive network requests.
    """

    CACHE_DURATION_SECONDS = 30  # Cache result for 30 seconds

    def __init__(self, cloud_url='http://localhost:8000'):
        """
        Initialize checker.

        Args:
            cloud_url: Base URL of Cloud API
        """
        self.cloud_url = cloud_url.rstrip('/')
        self._cache_key = 'cloud_connectivity_status'

    def is_online(self):
        """
        Check if Cloud is reachable.

        Returns:
            bool: True if online, False if offline

        Note: Result is cached for CACHE_DURATION_SECONDS
        """
        # Check cache first
        cached_status = cache.get(self._cache_key)
        if cached_status is not None:
            logger.debug(f"Using cached connectivity status: {cached_status}")
            return cached_status

        # Perform actual check
        status = self._check_connectivity()

        # Cache result
        cache.set(self._cache_key, status, timeout=self.CACHE_DURATION_SECONDS)

        return status

    def _check_connectivity(self):
        """
        Perform actual connectivity check.

        Returns:
            bool: True if Cloud is reachable, False otherwise
        """
        try:
            # GET request to /health/ endpoint (Cloud's health check)
            url = f"{self.cloud_url}/health/"
            response = requests.get(url, timeout=5)

            # Consider 2xx as "online"
            online = response.status_code == 200

            logger.info(f"Connectivity check: {'online' if online else 'offline'} (status: {response.status_code})")
            return online

        except requests.exceptions.RequestException as e:
            logger.warning(f"Connectivity check failed: {e}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error during connectivity check: {e}")
            return False

    def force_check(self):
        """
        Force connectivity check, bypassing cache.

        Returns:
            bool: True if online, False if offline
        """
        # Clear cache
        cache.delete(self._cache_key)

        # Perform check
        return self.is_online()


# Global singleton
_checker_instance = None


def get_connectivity_checker(cloud_url='http://localhost:8000'):
    """
    Get or create ConnectivityChecker singleton.

    Args:
        cloud_url: Base URL of Cloud API

    Returns:
        ConnectivityChecker: Singleton instance
    """
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = ConnectivityChecker(cloud_url=cloud_url)
    return _checker_instance
