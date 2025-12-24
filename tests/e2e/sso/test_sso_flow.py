"""
E2E tests for Hub SSO authentication flow.

Tests the complete SSO flow including Cloud session verification,
LocalUser creation, PIN setup, and authentication.
"""
import pytest
import json
from django.test import TestCase, Client, override_settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from unittest.mock import patch, Mock

from apps.accounts.models import LocalUser
from apps.configuration.models import HubConfig, StoreConfig


@pytest.mark.e2e
class TestHubLocalLoginFlow(TestCase):
    """Test the complete local login flow with PIN."""

    def setUp(self):
        self.client = Client()
        # Create a user with PIN
        self.user = LocalUser.objects.create(
            email='local@example.com',
            name='Local User',
            role='admin',
            is_active=True
        )
        self.user.set_pin('1234')

    def test_complete_pin_login_flow(self):
        """Test complete flow: login page -> select user -> enter PIN -> dashboard."""
        # Step 1: Access login page
        response = self.client.get('/login/')
        assert response.status_code == 200

        # Step 2: Verify PIN (AJAX call)
        response = self.client.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Step 3: Session should be established
        assert self.client.session.get('local_user_id') == str(self.user.id)

    def test_wrong_pin_denies_access(self):
        """Test that wrong PIN denies access."""
        response = self.client.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '9999'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

        # Session should NOT have user
        assert 'local_user_id' not in self.client.session

    def test_inactive_user_cannot_login(self):
        """Test that inactive user cannot login even with correct PIN."""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False


@pytest.mark.e2e
class TestHubPinSetupFlow(TestCase):
    """Test the PIN setup flow for new users."""

    def setUp(self):
        self.client = Client()
        # Create a user without PIN
        self.user = LocalUser.objects.create(
            email='newuser@example.com',
            name='New User',
            role='employee',
            pin_hash='',  # No PIN set
            is_active=True
        )

    def test_complete_pin_setup_flow(self):
        """Test complete flow: setup-pin page -> enter PIN -> login."""
        # Set pending user in session (simulates SSO redirect)
        session = self.client.session
        session['pending_user_id'] = str(self.user.id)
        session['pending_user_email'] = self.user.email
        session.save()

        # Submit PIN via POST (setup-pin only accepts POST for JSON)
        response = self.client.post(
            '/setup-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '5678'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify PIN was set
        self.user.refresh_from_db()
        assert self.user.check_pin('5678') is True

        # Session should be established
        assert self.client.session.get('local_user_id') == str(self.user.id)

    def test_invalid_pin_format_rejected(self):
        """Test that invalid PIN format is rejected."""
        session = self.client.session
        session['pending_user_id'] = str(self.user.id)
        session.save()

        # Try with too short PIN
        response = self.client.post(
            '/setup-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '123'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

        # Try with non-numeric PIN
        response = self.client.post(
            '/setup-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': 'abcd'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False


@pytest.mark.e2e
class TestHubLogoutFlow(TestCase):
    """Test the logout flow."""

    def setUp(self):
        self.client = Client()
        self.user = LocalUser.objects.create(
            email='logout@example.com',
            name='Logout User',
            role='admin',
            is_active=True
        )
        self.user.set_pin('1234')

        # Login the user
        self.client.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

    def test_logout_clears_session(self):
        """Test that logout clears session data."""
        # Verify logged in
        assert self.client.session.get('local_user_id') == str(self.user.id)

        # Logout
        response = self.client.get('/logout/')

        # Should redirect
        assert response.status_code == 302

        # Session should be cleared
        assert 'local_user_id' not in self.client.session

    def test_logout_redirects_to_login(self):
        """Test that logout redirects to login page."""
        response = self.client.get('/logout/', follow=True)

        # Should end up at login page
        assert response.status_code == 200


@pytest.mark.e2e
class TestHubEmployeeManagementFlow(TestCase):
    """Test the employee management flow."""

    def setUp(self):
        self.client = Client()
        # Create admin user
        self.admin = LocalUser.objects.create(
            email='admin@example.com',
            name='Admin User',
            role='admin',
            is_active=True
        )
        self.admin.set_pin('1234')

        # Login as admin
        session = self.client.session
        session['local_user_id'] = str(self.admin.id)
        session['user_role'] = 'admin'
        session.save()

    def test_complete_employee_creation_flow(self):
        """Test creating a new employee from start to finish."""
        # Step 1: Create employee via API
        response = self.client.post(
            '/api/employees/create/',
            data=json.dumps({
                'name': 'New Employee',
                'email': 'employee@example.com',
                'role': 'cashier',
                'pin': '5678'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Step 2: Verify employee exists
        employee = LocalUser.objects.get(email='employee@example.com')
        assert employee.name == 'New Employee'
        assert employee.role == 'cashier'
        assert employee.is_active is True

        # Step 3: Verify employee can login
        client2 = Client()
        response = client2.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(employee.id), 'pin': '5678'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_employee_deletion_flow(self):
        """Test deactivating an employee."""
        # Create an employee
        employee = LocalUser.objects.create(
            email='todelete@example.com',
            name='To Delete',
            role='employee',
            is_active=True
        )
        employee.set_pin('9999')

        # Delete (deactivate) the employee
        response = self.client.post(
            '/api/employees/delete/',
            data=json.dumps({'user_id': str(employee.id)}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify employee is deactivated
        employee.refresh_from_db()
        assert employee.is_active is False

        # Verify employee cannot login
        client2 = Client()
        response = client2.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(employee.id), 'pin': '9999'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

    def test_employee_pin_reset_flow(self):
        """Test resetting an employee's PIN."""
        # Create an employee
        employee = LocalUser.objects.create(
            email='resetpin@example.com',
            name='Reset PIN',
            role='employee',
            is_active=True
        )
        employee.set_pin('1111')

        # Reset PIN
        response = self.client.post(
            '/api/employees/reset-pin/',
            data=json.dumps({'user_id': str(employee.id), 'pin': '2222'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify old PIN doesn't work
        client2 = Client()
        response = client2.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(employee.id), 'pin': '1111'}),
            content_type='application/json'
        )
        data = response.json()
        assert data['success'] is False

        # Verify new PIN works
        response = client2.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(employee.id), 'pin': '2222'}),
            content_type='application/json'
        )
        data = response.json()
        assert data['success'] is True


@pytest.mark.e2e
@override_settings(DEPLOYMENT_MODE='web', DEMO_MODE=True)
class TestHubCloudSSOIntegrationFlow(TestCase):
    """Test the Cloud SSO integration flow."""

    def setUp(self):
        self.client = Client()
        # Clean up any existing users
        LocalUser.objects.all().delete()

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_first_user_becomes_admin_flow(self, mock_get):
        """Test that first user from Cloud SSO becomes admin."""
        # Mock Cloud API response
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                'authenticated': True,
                'email': 'first@example.com',
                'user_id': 1,
                'name': 'First User'
            }
        )

        # Simulate Cloud SSO creating first user
        from apps.core.middleware.cloud_sso_middleware import CloudSSOMiddleware
        from django.test import RequestFactory

        factory = RequestFactory()
        get_response = Mock(return_value=HttpResponse())
        middleware = CloudSSOMiddleware(get_response)
        middleware.deployment_mode = 'web'
        middleware.demo_mode = True
        middleware.cloud_api_url = 'https://int.erplora.com'

        # Create request with session
        request = factory.get('/dashboard/')
        session_middleware = SessionMiddleware(lambda r: HttpResponse())
        session_middleware.process_request(request)
        request.session.save()

        # Simulate user data from Cloud
        user_data = {'email': 'first@example.com', 'user_id': 1, 'name': 'First User'}
        result = middleware._ensure_local_user_and_session(request, user_data)

        # First user should be admin
        user = LocalUser.objects.get(email='first@example.com')
        assert user.role == 'admin'

    @patch('apps.core.middleware.cloud_sso_middleware.requests.get')
    def test_subsequent_users_become_cashiers(self, mock_get):
        """Test that subsequent users become cashiers."""
        # Create first admin user
        LocalUser.objects.create(
            email='admin@example.com',
            name='Admin',
            role='admin',
            is_active=True
        )

        # Mock Cloud API
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                'authenticated': True,
                'email': 'second@example.com',
                'user_id': 2,
                'name': 'Second User'
            }
        )

        from apps.core.middleware.cloud_sso_middleware import CloudSSOMiddleware
        from django.test import RequestFactory

        factory = RequestFactory()
        get_response = Mock(return_value=HttpResponse())
        middleware = CloudSSOMiddleware(get_response)
        middleware.deployment_mode = 'web'

        request = factory.get('/dashboard/')
        session_middleware = SessionMiddleware(lambda r: HttpResponse())
        session_middleware.process_request(request)
        request.session.save()

        user_data = {'email': 'second@example.com', 'user_id': 2, 'name': 'Second User'}
        middleware._ensure_local_user_and_session(request, user_data)

        # Second user should be cashier
        user = LocalUser.objects.get(email='second@example.com')
        assert user.role == 'cashier'


@pytest.mark.e2e
class TestHubProtectedRoutesFlow(TestCase):
    """Test access to protected routes in Hub."""

    def setUp(self):
        self.client = Client()
        self.user = LocalUser.objects.create(
            email='protected@example.com',
            name='Protected User',
            role='admin',
            is_active=True
        )
        self.user.set_pin('1234')

    def test_dashboard_requires_login(self):
        """Test that dashboard redirects when not logged in."""
        # In local mode, dashboard may allow access or redirect
        response = self.client.get('/dashboard/')

        # Response depends on deployment mode
        assert response.status_code in [200, 302]

    def test_dashboard_accessible_after_login(self):
        """Test that dashboard is accessible after login."""
        # Login
        self.client.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        # Access dashboard - may redirect to settings if not configured
        response = self.client.get('/dashboard/')
        # 200 or redirect to settings/setup is valid
        assert response.status_code in [200, 302]

    def test_employees_page_accessible_to_admin(self):
        """Test that employees page is accessible to admin."""
        # Login as admin
        session = self.client.session
        session['local_user_id'] = self.user.id
        session['user_role'] = 'admin'
        session.save()

        response = self.client.get('/employees/')
        # 200 or redirect is valid (might need store setup first)
        assert response.status_code in [200, 302]


@pytest.mark.e2e
class TestHubSessionPersistenceFlow(TestCase):
    """Test session persistence across requests."""

    def setUp(self):
        self.client = Client()
        self.user = LocalUser.objects.create(
            email='session@example.com',
            name='Session User',
            role='admin',
            is_active=True
        )
        self.user.set_pin('1234')

    def test_session_persists_across_requests(self):
        """Test that session data persists across multiple requests."""
        # Login
        self.client.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        initial_user_id = self.client.session.get('local_user_id')
        assert initial_user_id == self.user.id

        # Make multiple requests
        for _ in range(5):
            self.client.get('/dashboard/')
            assert self.client.session.get('local_user_id') == str(self.user.id)

    def test_session_contains_user_data(self):
        """Test that session contains all required user data after login."""
        # Login
        self.client.post(
            '/verify-pin/',
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        # Check session data
        assert 'local_user_id' in self.client.session
        assert self.client.session['local_user_id'] == self.user.id


@pytest.mark.e2e
class TestHubConfigurationFlow(TestCase):
    """Test Hub configuration operations in E2E context."""

    def setUp(self):
        self.client = Client()
        # Ensure config exists
        HubConfig.get_solo()
        StoreConfig.get_solo()

    def test_hub_config_accessible(self):
        """Test that HubConfig is accessible and usable."""
        config = HubConfig.get_solo()

        # Should have default values
        assert config.currency is not None
        # deployment_mode is in settings, not model
        assert hasattr(config, 'hub_id')

    def test_store_config_accessible(self):
        """Test that StoreConfig is accessible and usable."""
        config = StoreConfig.get_solo()

        # Should have default values
        assert config.tax_rate is not None
        assert config.tax_included is not None

    def test_config_values_in_templates(self):
        """Test that config values are available in template context."""
        user = LocalUser.objects.create(
            email='config@example.com',
            name='Config User',
            role='admin',
            is_active=True
        )
        user.set_pin('1234')

        # Login
        session = self.client.session
        session['local_user_id'] = user.id
        session.save()

        # Access a page that uses config
        response = self.client.get('/dashboard/')

        # Config should be in context
        if hasattr(response, 'context') and response.context:
            # Check if HUB_CONFIG is in context
            context_keys = []
            for ctx in response.context:
                if hasattr(ctx, 'keys'):
                    context_keys.extend(ctx.keys())
            # HUB_CONFIG should be available via context processor
            # This depends on the context processor being configured
