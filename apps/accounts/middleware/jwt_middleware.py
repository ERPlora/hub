"""
JWT Middleware.

Validates JWT tokens and handles offline mode with PIN authentication.
"""
import logging
from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpResponse

from apps.core.services.connectivity import get_connectivity_checker
from apps.core.services.public_key_fetcher import get_public_key_fetcher
from apps.core.services.jwt_validator import get_jwt_validator, TokenExpired, InvalidSignature

logger = logging.getLogger(__name__)


class JWTMiddleware:
    """
    Middleware for JWT validation with offline mode support.

    Flow:
    1. Check if Cloud is online
    2. If online: Validate JWT normally
    3. If offline + valid JWT: Allow with warning flag
    4. If offline + expired JWT: Redirect to PIN login
    """

    # Paths that require exact match (no prefix matching)
    EXEMPT_EXACT = ['/login/']

    # Paths that use prefix matching (any path starting with these)
    EXEMPT_PREFIXES = [
        '/verify-pin/',
        '/cloud-login/',
        '/setup-pin/',
        '/setup/',  # Setup wizard (before first login)
        '/static/',
        '/media/',
        '/api/',  # API endpoints handle their own auth
    ]

    def __init__(self, get_response):
        """Initialize middleware."""
        self.get_response = get_response
        # Don't initialize singletons here to make testing easier
        self.connectivity_checker = None
        self.public_key_fetcher = None
        self.jwt_validator = None

    def __call__(self, request):
        """Process request."""
        # Initialize singletons lazily
        if not self.connectivity_checker:
            self.connectivity_checker = get_connectivity_checker()
        if not self.public_key_fetcher:
            self.public_key_fetcher = get_public_key_fetcher()
        if not self.jwt_validator:
            self.jwt_validator = get_jwt_validator()

        # Check if path is exempt
        if self._is_exempt_path(request.path):
            return self.get_response(request)

        # Check if already authenticated via local PIN login
        # (local_user_id in session means authenticated via PIN)
        if request.session.get('local_user_id'):
            return self.get_response(request)

        # Get JWT token from session
        jwt_token = request.session.get('jwt_token')

        if not jwt_token:
            # No token and no local session - redirect to login
            return redirect(reverse('auth:login'))

        # Check connectivity
        is_online = self.connectivity_checker.is_online()

        # Get public key (from Cloud if online, from cache if offline)
        public_key = self.public_key_fetcher.fetch()

        if not public_key:
            # No public key available - cannot validate
            logger.error("No public key available for JWT validation")
            return HttpResponse("Service unavailable", status=503)

        # Validate JWT
        try:
            payload = self.jwt_validator.validate(jwt_token, public_key)

            # Token is valid
            request.user_id = payload.get('user_id')
            request.is_offline = not is_online

            if request.is_offline:
                logger.info("Request processed in offline mode with valid JWT")

            return self.get_response(request)

        except TokenExpired:
            # Token expired
            if is_online:
                # Online - redirect to login to get new token
                logger.info("JWT expired in online mode - redirecting to login")
                return redirect(reverse('auth:login'))
            else:
                # Offline - redirect to login (PIN login)
                logger.info("JWT expired in offline mode - redirecting to login (PIN)")
                return redirect(reverse('auth:login'))

        except (InvalidSignature, Exception) as e:
            # Invalid token
            logger.error(f"JWT validation failed: {e}")
            return redirect(reverse('auth:login'))

    def _is_exempt_path(self, path):
        """
        Check if path is exempt from authentication.

        Args:
            path: Request path

        Returns:
            bool: True if exempt, False otherwise
        """
        # Check exact matches first
        if path in self.EXEMPT_EXACT:
            return True

        # Check prefix matches
        for prefix in self.EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return True

        return False
