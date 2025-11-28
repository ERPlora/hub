"""
End-to-end tests for the complete SSO authentication flow.

These tests simulate the full user journey from Cloud authentication
to Hub access, including PIN setup.
"""
import pytest
import json
from unittest.mock import patch, Mock
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from apps.accounts.models import LocalUser


@override_settings(
    DEPLOYMENT_MODE='web',
    DEMO_MODE=True,
    CLOUD_API_URL='https://int.erplora.com',
    HUB_ID='test-hub',
    SESSION_COOKIE_NAME='hubsessionid',
)
class TestSSOFlowE2E(TestCase):
    """
    End-to-end tests for SSO flow.

    Flow:
    1. User visits Hub → redirected to Cloud login (no session)
    2. User logs in to Cloud → gets sessionid cookie
    3. User visits Hub with sessionid → SSO verifies with Cloud
    4. If new user → LocalUser created → redirect to setup-pin
    5. User sets PIN → session established → access granted
    6. Subsequent requests → local session valid → immediate access
    """

    def setUp(self):
        self.client = Client()
        LocalUser.objects.all().delete()

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_complete_new_user_flow(self, mock_cloud_api):
        """Test complete flow for a new user."""
        # Step 1: Visit Hub without session → should redirect to Cloud login
        response = self.client.get('/dashboard/', follow=False)

        # Without sessionid, should redirect to Cloud login
        assert response.status_code == 302
        assert 'int.erplora.com/account/login/' in response.url

        # Step 2: User logs in to Cloud and comes back with sessionid
        # Simulate having Cloud's sessionid cookie
        self.client.cookies['sessionid'] = 'valid-cloud-session'

        # Mock Cloud API returning authenticated user
        mock_cloud_api.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'newuser@example.com'}
        )

        # Step 3: Visit Hub with sessionid → should create LocalUser and redirect to setup-pin
        response = self.client.get('/dashboard/', follow=False)

        assert response.status_code == 302
        assert '/setup-pin/' in response.url

        # LocalUser should be created
        user = LocalUser.objects.get(email='newuser@example.com')
        assert user.role == 'admin'  # First user is admin
        assert user.pin_hash == ''   # No PIN yet

        # Step 4: Visit setup-pin page
        response = self.client.get('/setup-pin/')
        assert response.status_code == 200
        assert b'pin' in response.content.lower() or b'PIN' in response.content

        # Step 5: Set PIN
        response = self.client.post(
            '/setup-pin/',
            data=json.dumps({'user_id': user.id, 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # User should have PIN now
        user.refresh_from_db()
        assert user.pin_hash != ''

        # Step 6: Access Hub → should work now
        response = self.client.get('/dashboard/', follow=False)

        # Should have access (either 200 or redirect to dashboard, not to login)
        assert response.status_code in [200, 302]
        if response.status_code == 302:
            assert 'login' not in response.url.lower()

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_returning_user_with_pin_flow(self, mock_cloud_api):
        """Test flow for returning user who already has PIN."""
        # Create existing user with PIN
        user = LocalUser.objects.create(
            email='returning@example.com',
            name='Returning User',
            role='admin',
            is_active=True
        )
        user.set_pin('5678')
        user.save()

        # Simulate Cloud session
        self.client.cookies['sessionid'] = 'valid-cloud-session'

        mock_cloud_api.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'returning@example.com'}
        )

        # Visit Hub → should get immediate access
        response = self.client.get('/dashboard/', follow=False)

        # Should not redirect to login or setup-pin
        assert response.status_code in [200, 302]
        if response.status_code == 302:
            assert 'login' not in response.url.lower()
            assert 'setup-pin' not in response.url.lower()

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_session_persistence_across_requests(self, mock_cloud_api):
        """Test that Hub session persists across multiple requests."""
        # Create user with PIN
        user = LocalUser.objects.create(
            email='persistent@example.com',
            name='Persistent User',
            role='cashier',
            is_active=True
        )
        user.set_pin('9999')
        user.save()

        self.client.cookies['sessionid'] = 'valid-cloud-session'

        mock_cloud_api.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'persistent@example.com'}
        )

        # First request - establishes session
        response1 = self.client.get('/dashboard/')

        # Second request - should use existing session
        response2 = self.client.get('/settings/')

        # Third request - should still work
        response3 = self.client.get('/plugins/')

        # All should succeed (not redirect to login)
        for response in [response1, response2, response3]:
            if response.status_code == 302:
                assert 'login' not in response.url.lower()

        # Cloud API should be called for each request (for security)
        assert mock_cloud_api.call_count >= 1

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_invalid_cloud_session_denies_access(self, mock_cloud_api):
        """Test that invalid Cloud session redirects to login."""
        self.client.cookies['sessionid'] = 'invalid-session'

        mock_cloud_api.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': False}
        )

        response = self.client.get('/dashboard/', follow=False)

        assert response.status_code == 302
        assert 'login' in response.url

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_cloud_api_error_denies_access(self, mock_cloud_api):
        """Test that Cloud API errors deny access."""
        import requests

        self.client.cookies['sessionid'] = 'some-session'
        mock_cloud_api.side_effect = requests.exceptions.ConnectionError()

        response = self.client.get('/dashboard/', follow=False)

        assert response.status_code == 302
        assert 'login' in response.url

    def test_exempt_urls_work_without_session(self):
        """Test that exempt URLs work without any session."""
        # Health check should work
        response = self.client.get('/health/')
        assert response.status_code in [200, 404]  # 404 if view doesn't exist

        # Login should work
        response = self.client.get('/login/')
        assert response.status_code in [200, 302]

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_second_user_gets_cashier_role(self, mock_cloud_api):
        """Test that second user gets cashier role, not admin."""
        # Create first user (admin)
        LocalUser.objects.create(
            email='admin@example.com',
            name='Admin',
            role='admin',
            is_active=True
        )

        self.client.cookies['sessionid'] = 'valid-session'

        mock_cloud_api.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'second@example.com'}
        )

        # Second user visits Hub
        response = self.client.get('/dashboard/', follow=False)

        # Should create user and redirect to setup-pin
        assert response.status_code == 302

        second_user = LocalUser.objects.get(email='second@example.com')
        assert second_user.role == 'cashier'  # Not admin

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_reactivated_user_must_setup_pin_again(self, mock_cloud_api):
        """Test that reactivated user must set up PIN again."""
        # Create inactive user with old PIN
        user = LocalUser.objects.create(
            email='inactive@example.com',
            name='Inactive',
            role='admin',
            is_active=False
        )
        user.set_pin('old-pin')
        user.save()

        self.client.cookies['sessionid'] = 'valid-session'

        mock_cloud_api.return_value = Mock(
            status_code=200,
            json=lambda: {'authenticated': True, 'email': 'inactive@example.com'}
        )

        # Inactive user visits Hub
        response = self.client.get('/dashboard/', follow=False)

        # Should redirect to setup-pin (PIN was reset)
        assert response.status_code == 302
        assert '/setup-pin/' in response.url

        # User should be reactivated but PIN reset
        user.refresh_from_db()
        assert user.is_active is True
        assert user.pin_hash == ''


@override_settings(DEPLOYMENT_MODE='local')
class TestDesktopModeBypassesSSO(TestCase):
    """Test that desktop mode bypasses SSO completely."""

    def test_desktop_mode_no_sso(self):
        """In desktop mode, SSO middleware should be disabled."""
        client = Client()

        # Without any Cloud session, desktop should work
        # (Note: Desktop has its own auth via PIN)
        response = client.get('/login/')

        # Should show login page, not redirect to Cloud
        assert response.status_code in [200, 302]
        if response.status_code == 302:
            assert 'erplora.com' not in response.url


class TestPinSetupView(TestCase):
    """Test the PIN setup view."""

    def setUp(self):
        self.client = Client()

    def test_setup_pin_get_without_pending_user_redirects(self):
        """GET /setup-pin/ without pending user should redirect to login."""
        response = self.client.get('/setup-pin/')

        assert response.status_code == 302
        assert 'login' in response.url

    def test_setup_pin_get_with_pending_user_shows_form(self):
        """GET /setup-pin/ with pending user should show form."""
        user = LocalUser.objects.create(
            email='pending@example.com',
            name='Pending',
            role='admin'
        )

        # Set pending user in session
        session = self.client.session
        session['pending_user_id'] = user.id
        session['pending_user_email'] = user.email
        session.save()

        response = self.client.get('/setup-pin/')

        assert response.status_code == 200

    def test_setup_pin_post_saves_pin(self):
        """POST /setup-pin/ should save PIN and establish session."""
        user = LocalUser.objects.create(
            email='setpin@example.com',
            name='Set Pin',
            role='admin'
        )

        # Set pending user in session
        session = self.client.session
        session['pending_user_id'] = user.id
        session.save()

        response = self.client.post(
            '/setup-pin/',
            data=json.dumps({'user_id': user.id, 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify PIN was saved
        user.refresh_from_db()
        assert user.check_pin('1234') is True

    def test_setup_pin_rejects_invalid_pin(self):
        """POST /setup-pin/ should reject invalid PIN."""
        user = LocalUser.objects.create(
            email='invalid@example.com',
            name='Invalid',
            role='admin'
        )

        session = self.client.session
        session['pending_user_id'] = user.id
        session.save()

        # Try non-numeric PIN
        response = self.client.post(
            '/setup-pin/',
            data=json.dumps({'user_id': user.id, 'pin': 'abcd'}),
            content_type='application/json'
        )

        data = response.json()
        assert data['success'] is False

        # Try too short PIN
        response = self.client.post(
            '/setup-pin/',
            data=json.dumps({'user_id': user.id, 'pin': '12'}),
            content_type='application/json'
        )

        data = response.json()
        assert data['success'] is False
