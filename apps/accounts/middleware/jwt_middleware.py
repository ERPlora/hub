"""
Authentication Middleware.

Ensures every request has a local user session (profile + PIN).
Cloud session (JWT) is handled separately by the login views.
"""
import logging
from django.shortcuts import redirect
from django.urls import resolve, reverse, Resolver404

logger = logging.getLogger(__name__)


class JWTMiddleware:
    """
    Middleware that requires PIN authentication for all Hub pages.

    Flow:
    1. Exempt paths (login, static, API, etc.) pass through
    2. Public views (@public_view decorator) pass through
    3. If local_user_id in session (PIN authenticated) → allow
    4. Otherwise → redirect to login (profile selection + PIN)

    Cloud session (JWT tokens) persists in the session cookie so
    users don't need to re-enter Cloud credentials. But they must
    always select their profile and enter PIN to access the Hub.
    """

    # Paths that require exact match (no prefix matching)
    EXEMPT_EXACT = ['/login/']

    # Paths that use prefix matching (any path starting with these)
    EXEMPT_PREFIXES = [
        '/verify-pin/',
        '/get-employees/',
        '/cloud-login/',
        '/setup-pin/',
        '/verify-device-trust/',
        '/trust-device/',
        '/revoke-device/',
        '/static/',
        '/media/',
        '/api/',  # API endpoints handle their own auth
        '/manifest.json',  # PWA manifest
        '/serviceworker.js',  # Service worker
        '/health/',  # Health check endpoint
        '/ht/',  # django-health-check endpoint
        '/favicon.ico',
        '/set-language/',
        '/logout/',
        '/public/',  # Public pages (catalog, etc.)
    ]

    def __init__(self, get_response):
        """Initialize middleware."""
        self.get_response = get_response

    def __call__(self, request):
        """Process request."""
        # Check if path is exempt
        if self._is_exempt_path(request.path):
            return self.get_response(request)

        # Check if the view is marked as public (via @public_view decorator)
        if self._is_public_view(request.path):
            return self.get_response(request)

        # Check if already authenticated via local PIN login
        # (local_user_id in session means authenticated via PIN)
        if request.session.get('local_user_id'):
            return self.get_response(request)

        # No PIN session — redirect to login for profile selection + PIN
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

    def _is_public_view(self, path):
        """
        Check if the resolved view is marked as public via @public_view decorator.

        Views decorated with @public_view have is_public=True set on the
        function object. This allows module views (e.g. checkout pages,
        webhook endpoints) to opt out of authentication.

        Args:
            path: Request path

        Returns:
            bool: True if the view is marked as public, False otherwise
        """
        try:
            match = resolve(path)
            return getattr(match.func, 'is_public', False)
        except Resolver404:
            return False
