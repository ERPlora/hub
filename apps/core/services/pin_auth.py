"""
PIN Authentication Service.

Provides secure PIN-based authentication for offline mode.
"""
import logging
import hashlib
from datetime import datetime, timedelta
from django.core.cache import cache
from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


class PINLocked(Exception):
    """Raised when PIN is locked due to too many failed attempts."""
    pass


class PINAuth:
    """
    PIN-based authentication for offline mode.

    Features:
    - Secure PIN storage with SHA-256 hashing
    - Rate limiting (5 failed attempts = 15 min lockout)
    - 4-6 digit PIN support
    """

    MAX_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 15

    def __init__(self):
        """Initialize PIN auth."""
        self._pin_hash_key = 'hub_pin_hash'
        self._attempts_key = 'hub_pin_attempts'
        self._lockout_key = 'hub_pin_lockout'

    def set_pin(self, pin):
        """
        Set PIN for Hub.

        Args:
            pin: PIN string (4-6 digits)

        Raises:
            ValueError: If PIN format is invalid
        """
        # Validate PIN format
        if not pin or not isinstance(pin, str):
            raise ValueError(_("PIN must be a string"))

        if not pin.isdigit():
            raise ValueError(_("PIN must contain only digits"))

        if len(pin) < 4 or len(pin) > 6:
            raise ValueError(_("PIN must be 4-6 digits"))

        # Hash PIN with SHA-256
        pin_hash = self._hash_pin(pin)

        # Store in cache (persistent across restarts using database cache backend)
        cache.set(self._pin_hash_key, pin_hash, timeout=None)  # No expiry

        # Reset attempts and lockout
        cache.delete(self._attempts_key)
        cache.delete(self._lockout_key)

        logger.info("PIN set successfully")

    def has_pin(self):
        """
        Check if PIN is set.

        Returns:
            bool: True if PIN is set, False otherwise
        """
        return cache.get(self._pin_hash_key) is not None

    def validate(self, pin):
        """
        Validate PIN.

        Args:
            pin: PIN string to validate

        Returns:
            bool: True if PIN is correct, False otherwise

        Raises:
            PINLocked: If PIN is locked due to too many attempts
        """
        # Check if locked
        if self._is_locked():
            lockout_until = cache.get(self._lockout_key)
            raise PINLocked(f"PIN locked until {lockout_until}")

        # Get stored hash
        stored_hash = cache.get(self._pin_hash_key)
        if not stored_hash:
            logger.warning("PIN validation attempted but no PIN is set")
            return False

        # Hash provided PIN
        pin_hash = self._hash_pin(pin)

        # Compare hashes
        if pin_hash == stored_hash:
            # Correct PIN - reset attempts
            cache.delete(self._attempts_key)
            logger.info("PIN validated successfully")
            return True
        else:
            # Incorrect PIN - increment attempts
            self._increment_attempts()
            logger.warning("Incorrect PIN attempt")
            return False

    def _hash_pin(self, pin):
        """
        Hash PIN with SHA-256.

        Args:
            pin: PIN string

        Returns:
            str: Hashed PIN
        """
        # Use settings.SECRET_KEY as salt
        salt = settings.SECRET_KEY.encode('utf-8')
        pin_bytes = pin.encode('utf-8')

        return hashlib.sha256(salt + pin_bytes).hexdigest()

    def _increment_attempts(self):
        """Increment failed attempts counter and lock if needed."""
        attempts = cache.get(self._attempts_key, 0)
        attempts += 1
        cache.set(self._attempts_key, attempts, timeout=None)

        # Check if should lock
        if attempts >= self.MAX_ATTEMPTS:
            lockout_until = datetime.now() + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)
            cache.set(self._lockout_key, lockout_until, timeout=self.LOCKOUT_DURATION_MINUTES * 60)
            logger.warning(f"PIN locked until {lockout_until} after {attempts} failed attempts")

    def _is_locked(self):
        """
        Check if PIN is currently locked.

        Returns:
            bool: True if locked, False otherwise
        """
        lockout_until = cache.get(self._lockout_key)

        if not lockout_until:
            return False

        # Check if lockout has expired
        if datetime.now() > lockout_until:
            cache.delete(self._lockout_key)
            cache.delete(self._attempts_key)
            return False

        return True

    def get_remaining_attempts(self):
        """
        Get number of remaining attempts before lockout.

        Returns:
            int: Number of attempts remaining (0 if locked)
        """
        if self._is_locked():
            return 0

        attempts = cache.get(self._attempts_key, 0)
        return max(0, self.MAX_ATTEMPTS - attempts)


# Global singleton
_pin_auth_instance = None


def get_pin_auth():
    """
    Get or create PINAuth singleton.

    Returns:
        PINAuth: Singleton instance
    """
    global _pin_auth_instance
    if _pin_auth_instance is None:
        _pin_auth_instance = PINAuth()
    return _pin_auth_instance
