"""
Public Key Fetcher Service.

Fetches and caches RSA public key from Cloud for JWT validation.
"""
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_token_cache():
    """
    Get TokenCache model lazily to avoid circular imports.

    Returns:
        TokenCache: Token cache model instance
    """
    from apps.core.models import TokenCache
    return TokenCache.get_cache()


class PublicKeyFetchError(Exception):
    """Raised when public key cannot be fetched."""
    pass


class PublicKeyFetcher:
    """
    Fetches and caches RSA public key from Cloud API.

    The public key is used to validate JWT tokens locally without
    contacting the Cloud on every request.

    Key is cached for 24 hours before refresh.
    """

    CACHE_DURATION_HOURS = 24

    def __init__(self, cloud_url='http://localhost:8000'):
        """
        Initialize fetcher.

        Args:
            cloud_url: Base URL of Cloud API
        """
        self.cloud_url = cloud_url.rstrip('/')
        self._cached_key = None
        self._cache_timestamp = None

        # Cache file location
        self._cache_dir = Path(settings.BASE_DIR) / 'cache'
        self._cache_file = self._cache_dir / 'jwt_public_key.pem'

        # Load from database cache first, then disk cache
        self._load_from_database()
        if not self._cached_key:
            self._load_from_disk()

    def fetch(self):
        """
        Fetch public key from Cloud or cache.

        Returns:
            str: RSA public key in PEM format, or None if unavailable
        """
        # Check if cache is valid
        if self._is_cache_valid():
            logger.debug("Using cached public key")
            return self._cached_key

        # Try to fetch from Cloud
        try:
            logger.info("Fetching public key from Cloud")
            public_key = self._fetch_from_cloud()
            self._cache_key(public_key)
            self._save_to_database()
            self._save_to_disk()
            return public_key
        except Exception as e:
            logger.error(f"Failed to fetch public key from Cloud: {e}")

            # Fall back to cached key if available
            if self._cached_key:
                logger.warning("Using expired cached key due to network error")
                return self._cached_key

            return None

    def _fetch_from_cloud(self):
        """
        Fetch public key from Cloud API.

        Returns:
            str: Public key in PEM format

        Raises:
            PublicKeyFetchError: If fetch fails
        """
        url = f"{self.cloud_url}/api/auth/public-key/"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            public_key = response.text

            # Validate it looks like a PEM key
            if 'BEGIN PUBLIC KEY' not in public_key:
                raise PublicKeyFetchError("Invalid public key format")

            return public_key

        except requests.exceptions.RequestException as e:
            raise PublicKeyFetchError(f"HTTP error: {e}")

    def _cache_key(self, public_key):
        """
        Cache public key in memory.

        Args:
            public_key: Public key to cache
        """
        self._cached_key = public_key
        self._cache_timestamp = datetime.now()

    def _is_cache_valid(self):
        """
        Check if cached key is still valid.

        Returns:
            bool: True if cache is valid, False otherwise
        """
        if not self._cached_key or not self._cache_timestamp:
            return False

        age = datetime.now() - self._cache_timestamp
        max_age = timedelta(hours=self.CACHE_DURATION_HOURS)

        return age < max_age

    def _save_to_disk(self):
        """Save cached key to disk for persistence."""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(self._cached_key)
            logger.debug(f"Saved public key to {self._cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save public key to disk: {e}")

    def _load_from_disk(self):
        """Load cached key from disk if available."""
        try:
            if self._cache_file.exists():
                self._cached_key = self._cache_file.read_text()
                # Use file modification time as cache timestamp
                mtime = self._cache_file.stat().st_mtime
                self._cache_timestamp = datetime.fromtimestamp(mtime)
                logger.debug(f"Loaded public key from {self._cache_file}")
        except Exception as e:
            logger.warning(f"Failed to load public key from disk: {e}")

    def _save_to_database(self):
        """Save public key to database cache."""
        try:
            token_cache = _get_token_cache()
            token_cache.cache_public_key(self._cached_key)
            logger.debug("Saved public key to database cache")
        except Exception as e:
            logger.warning(f"Failed to save public key to database: {e}")

    def _load_from_database(self):
        """Load cached key from database if available."""
        try:
            token_cache = _get_token_cache()
            cached_key = token_cache.get_cached_public_key()
            if cached_key:
                self._cached_key = cached_key
                # Use database timestamp
                if token_cache.public_key_cached_at:
                    self._cache_timestamp = token_cache.public_key_cached_at
                logger.debug("Loaded public key from database cache")
        except Exception as e:
            logger.warning(f"Failed to load public key from database: {e}")


# Global singleton
_fetcher_instance = None


def get_public_key_fetcher(cloud_url='http://localhost:8000'):
    """
    Get or create PublicKeyFetcher singleton.

    Args:
        cloud_url: Base URL of Cloud API

    Returns:
        PublicKeyFetcher: Singleton instance
    """
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = PublicKeyFetcher(cloud_url=cloud_url)
    return _fetcher_instance
