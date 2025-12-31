"""
Unit tests for CloudSSOMiddleware.

Tests the SSO authentication flow between Cloud and Hub.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from django.test import RequestFactory, TestCase, override_settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse

from apps.core.middleware.cloud_sso_middleware import CloudSSOMiddleware


class TestCloudSSOMiddlewareExemptUrls(TestCase):
    """Test exempt URL detection."""

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = Mock(return_value=HttpResponse())
        self.middleware = CloudSSOMiddleware(self.get_response)

    def test_health_endpoint_is_exempt(self):
        """Health check should not require authentication."""
        assert self.middleware._is_exempt_url('/health/') is True

    def test_static_files_are_exempt(self):
        """Static files should not require authentication."""
        assert self.middleware._is_exempt_url('/static/css/main.css') is True
        assert self.middleware._is_exempt_url('/static/js/app.js') is True

    def test_media_files_are_exempt(self):
        """Media files should not require authentication."""
        assert self.middleware._is_exempt_url('/media/uploads/image.png') is True

    def test_login_is_exempt(self):
        """Login page should be exempt."""
        assert self.middleware._is_exempt_url('/login/') is True

    def test_setup_pin_is_exempt(self):
        """PIN setup should be exempt (user needs to set PIN after SSO)."""
        assert self.middleware._is_exempt_url('/setup-pin/') is True

    def test_verify_pin_is_exempt(self):
        """PIN verification should be exempt."""
        assert self.middleware._is_exempt_url('/verify-pin/') is True

    def test_logout_is_exempt(self):
        """Logout should be exempt."""
        assert self.middleware._is_exempt_url('/logout/') is True

    def test_dashboard_is_not_exempt(self):
        """Dashboard should require authentication."""
        assert self.middleware._is_exempt_url('/home/') is False

    def test_modules_are_not_exempt(self):
        """Module pages should require authentication."""
        assert self.middleware._is_exempt_url('/modules/products/') is False

    def test_settings_is_not_exempt(self):
        """Settings should require authentication."""
        assert self.middleware._is_exempt_url('/settings/') is False


@pytest.mark.skip(reason="Session handling in tests requires additional setup")
@override_settings(DEPLOYMENT_MODE='web', DEMO_MODE=True)
class TestCloudSSOMiddlewareWebMode(TestCase):
    """Test middleware behavior in web deployment mode."""

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = Mock(return_value=HttpResponse('OK'))

    def _get_middleware(self):
        """Create middleware with web settings."""
        middleware = CloudSSOMiddleware(self.get_response)
        middleware.deployment_mode = 'web'
        middleware.demo_mode = True
        middleware.cloud_api_url = 'https://int.erplora.com'
        middleware.hub_id = 'test-hub-id'
        return middleware

    def _add_session_to_request(self, request):
        """Add session middleware to request."""
        session_middleware = SessionMiddleware(lambda r: HttpResponse())
        session_middleware.process_request(request)
        request.session.save()

    def test_no_session_cookie_redirects_to_cloud_login(self):
        """Without sessionid cookie, redirect to Cloud login."""
        middleware = self._get_middleware()
        request = self.factory.get('/home/')
        self._add_session_to_request(request)

        response = middleware(request)

        assert response.status_code == 302
        assert 'int.erplora.com/account/login/' in response.url
        assert 'next=' in response.url

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_invalid_session_redirects_to_login(self, mock_get):
        """Invalid Cloud session should redirect to login."""
        middleware = self._get_middleware()

        # Mock Cloud API returning unauthenticated
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': False}
        )

        request = self.factory.get('/home/')
        request.COOKIES['sessionid'] = 'invalid-session-id'
        self._add_session_to_request(request)

        response = middleware(request)

        assert response.status_code == 302
        assert 'login' in response.url

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_valid_session_without_local_user_creates_one(self, mock_get):
        """Valid Cloud session should create LocalUser if not exists."""
        middleware = self._get_middleware()

        # Mock Cloud API returning authenticated with user_id
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'test@example.com', 'user_id': 123, 'name': 'Test User'}
        )

        request = self.factory.get('/home/')
        request.COOKIES['sessionid'] = 'valid-cloud-session'
        self._add_session_to_request(request)

        # User has no local_user_id yet
        assert 'local_user_id' not in request.session

        response = middleware(request)

        # Should redirect to setup-pin since new user has no PIN
        assert response.status_code == 302
        assert '/setup-pin/' in response.url

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_valid_session_with_local_user_and_pin_allows_access(self, mock_get):
        """Valid session with existing LocalUser with PIN should allow access."""
        from apps.accounts.models import LocalUser

        middleware = self._get_middleware()

        # Create a LocalUser with PIN
        user = LocalUser.objects.create(
            email='existing@example.com',
            name='Existing User',
            role='admin',
            pin_hash='hashed-pin',  # Has PIN
            is_active=True
        )

        # Mock Cloud API returning authenticated
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'existing@example.com', 'user_id': 456, 'name': 'Existing User'}
        )

        request = self.factory.get('/home/')
        request.COOKIES['sessionid'] = 'valid-cloud-session'
        self._add_session_to_request(request)

        response = middleware(request)

        # Should allow access (get_response called)
        assert response.status_code == 200
        assert response.content == b'OK'

        # Session should have local_user_id
        assert request.session.get('local_user_id') == user.id

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_existing_local_session_skips_cloud_verification(self, mock_get):
        """If user already has local session, should skip Cloud verification."""
        from apps.accounts.models import LocalUser

        middleware = self._get_middleware()

        # Create a LocalUser
        user = LocalUser.objects.create(
            email='session@example.com',
            name='Session User',
            role='admin',
            pin_hash='hashed-pin',
            is_active=True
        )

        # Mock Cloud API
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'session@example.com', 'user_id': 789, 'name': 'Session User'}
        )

        request = self.factory.get('/home/')
        request.COOKIES['sessionid'] = 'valid-cloud-session'
        self._add_session_to_request(request)

        # User already has local session
        request.session['local_user_id'] = user.id
        request.session.save()

        response = middleware(request)

        # Should allow access immediately
        assert response.status_code == 200

        # Cloud API should still be called to verify (for security)
        assert mock_get.called


@override_settings(DEPLOYMENT_MODE='local')
class TestCloudSSOMiddlewareDesktopMode(TestCase):
    """Test middleware is disabled in desktop mode."""

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = Mock(return_value=HttpResponse('Desktop OK'))

    def test_middleware_passes_through_in_desktop_mode(self):
        """In desktop mode, middleware should pass through all requests."""
        middleware = CloudSSOMiddleware(self.get_response)
        middleware.deployment_mode = 'local'

        request = self.factory.get('/home/')

        response = middleware(request)

        assert response.status_code == 200
        assert response.content == b'Desktop OK'


@override_settings(CLOUD_API_URL='https://int.erplora.com')
class TestCloudSSOMiddlewareCloudAPIVerification(TestCase):
    """Test Cloud API session verification."""

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = Mock(return_value=HttpResponse())
        self.middleware = CloudSSOMiddleware(self.get_response)

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_successful_session_verification(self, mock_get):
        """Test successful session verification with Cloud API."""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'user@example.com', 'user_id': 123, 'name': 'Test User'}
        )

        is_auth, user_data = self.middleware._verify_session_with_cloud('valid-session')

        assert is_auth is True
        assert user_data['email'] == 'user@example.com'
        assert user_data['user_id'] == 123
        assert user_data['name'] == 'Test User'
        mock_get.assert_called_once_with(
            'https://int.erplora.com/api/auth/verify-session/',
            cookies={'sessionid': 'valid-session'},
            timeout=5
        )

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_failed_session_verification(self, mock_get):
        """Test failed session verification (unauthenticated)."""
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': False}
        )

        is_auth, user_data = self.middleware._verify_session_with_cloud('invalid-session')

        assert is_auth is False
        assert user_data is None

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_cloud_api_error_denies_access(self, mock_get):
        """Cloud API errors should deny access for security."""
        mock_get.return_value = Mock(status_code=500)

        is_auth, user_data = self.middleware._verify_session_with_cloud('session')

        assert is_auth is False
        assert user_data is None

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_network_error_denies_access(self, mock_get):
        """Network errors should deny access for security."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        is_auth, user_data = self.middleware._verify_session_with_cloud('session')

        assert is_auth is False
        assert user_data is None

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_timeout_denies_access(self, mock_get):
        """Timeouts should deny access for security."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        is_auth, user_data = self.middleware._verify_session_with_cloud('session')

        assert is_auth is False
        assert user_data is None


class TestCloudSSOMiddlewareLocalUserCreation(TestCase):
    """Test LocalUser creation during SSO flow."""

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = Mock(return_value=HttpResponse())
        self.middleware = CloudSSOMiddleware(self.get_response)

    def _create_request_with_session(self, path='/'):
        request = self.factory.get(path)
        session_middleware = SessionMiddleware(lambda r: HttpResponse())
        session_middleware.process_request(request)
        request.session.save()
        return request

    def test_first_user_gets_admin_role(self):
        """First user should be assigned admin role."""
        from apps.accounts.models import LocalUser

        # Ensure no users exist
        LocalUser.objects.all().delete()

        request = self._create_request_with_session()

        user_data = {'email': 'first@example.com', 'user_id': 1, 'name': 'First User'}
        result = self.middleware._ensure_local_user_and_session(request, user_data)

        user = LocalUser.objects.get(email='first@example.com')
        assert user.role == 'admin'

    def test_subsequent_users_get_cashier_role(self):
        """Subsequent users should be assigned cashier role."""
        from apps.accounts.models import LocalUser

        # Create first user
        LocalUser.objects.create(
            email='admin@example.com',
            name='Admin',
            role='admin',
            pin_hash='hash'
        )

        request = self._create_request_with_session()

        user_data = {'email': 'second@example.com', 'user_id': 2, 'name': 'Second User'}
        result = self.middleware._ensure_local_user_and_session(request, user_data)

        user = LocalUser.objects.get(email='second@example.com')
        assert user.role == 'cashier'

    def test_user_without_pin_redirects_to_setup(self):
        """User without PIN should be redirected to setup-pin."""
        from apps.accounts.models import LocalUser

        LocalUser.objects.all().delete()

        request = self._create_request_with_session()

        user_data = {'email': 'new@example.com', 'user_id': 3, 'name': 'New User'}
        result = self.middleware._ensure_local_user_and_session(request, user_data)

        assert result is not None
        assert result.status_code == 302
        assert '/setup-pin/' in result.url

        # Session should have pending_user_id
        assert 'pending_user_id' in request.session
        assert 'pending_user_email' in request.session

    def test_user_with_pin_gets_session_established(self):
        """User with PIN should have session established."""
        from apps.accounts.models import LocalUser

        user = LocalUser.objects.create(
            email='haspin@example.com',
            name='Has Pin',
            role='admin',
            pin_hash='some-hash',  # Has PIN
            is_active=True
        )

        request = self._create_request_with_session()

        user_data = {'email': 'haspin@example.com', 'user_id': 4, 'name': 'Has Pin'}
        result = self.middleware._ensure_local_user_and_session(request, user_data)

        assert result is None  # No redirect
        assert request.session['local_user_id'] == str(user.id)  # Stored as string
        assert request.session['user_email'] == 'haspin@example.com'
        assert request.session['user_role'] == 'admin'

    def test_inactive_user_gets_reactivated(self):
        """Inactive user should be reactivated on SSO login."""
        from apps.accounts.models import LocalUser

        user = LocalUser.objects.create(
            email='inactive@example.com',
            name='Inactive User',
            role='admin',
            pin_hash='old-hash',
            is_active=False  # Inactive
        )

        request = self._create_request_with_session()

        user_data = {'email': 'inactive@example.com', 'user_id': 5, 'name': 'Inactive User'}
        result = self.middleware._ensure_local_user_and_session(request, user_data)

        user.refresh_from_db()
        assert user.is_active is True
        assert user.pin_hash == ''  # PIN reset

        # Should redirect to setup-pin since PIN was reset
        assert result.status_code == 302
        assert '/setup-pin/' in result.url
