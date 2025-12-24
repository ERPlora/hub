"""
Unit tests for Hub accounts views.

Tests login, setup-pin, verify-pin, and logout views.
"""
import pytest
import json
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from unittest.mock import patch, Mock
from apps.accounts.models import LocalUser


class TestLoginView(TestCase):
    """Test the login view."""

    def setUp(self):
        self.client = Client()
        self.url = '/login/'

    def test_login_page_renders(self):
        """GET login should render the login template."""
        response = self.client.get(self.url)

        assert response.status_code == 200

    def test_login_page_shows_local_users(self):
        """Login page should include local users for PIN login."""
        user = LocalUser.objects.create(
            email='local@example.com',
            name='Local User',
            role='admin',
            pin_hash='somehash',
            is_active=True
        )

        response = self.client.get(self.url)

        assert response.status_code == 200
        # Check that user data is in context
        assert 'local_users_json' in response.context or b'Local User' in response.content


class TestVerifyPinView(TestCase):
    """Test PIN verification."""

    def setUp(self):
        self.client = Client()
        self.url = '/verify-pin/'
        self.user = LocalUser.objects.create(
            email='pin@example.com',
            name='PIN User',
            role='admin',
            pin_hash='',
            is_active=True
        )
        self.user.set_pin('1234')

    def test_verify_correct_pin(self):
        """Correct PIN should authenticate user."""
        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_verify_incorrect_pin(self):
        """Incorrect PIN should fail."""
        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id), 'pin': '9999'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

    def test_verify_nonexistent_user(self):
        """Non-existent user should fail."""
        import uuid
        fake_uuid = str(uuid.uuid4())
        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': fake_uuid, 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

    def test_verify_inactive_user(self):
        """Inactive user should fail."""
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

    def test_verify_missing_pin(self):
        """Missing PIN should fail."""
        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id)}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

    def test_verify_sets_session(self):
        """Successful verify should set session data."""
        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        assert self.client.session.get('local_user_id') == str(self.user.id)


class TestSetupPinView(TestCase):
    """Test PIN setup for new users."""

    def setUp(self):
        self.client = Client()
        self.url = '/setup-pin/'
        self.user = LocalUser.objects.create(
            email='setup@example.com',
            name='Setup User',
            role='admin',
            pin_hash='',  # No PIN yet
            is_active=True
        )

    def test_setup_pin_post_valid(self):
        """POST with valid PIN should set it."""
        session = self.client.session
        session['pending_user_id'] = str(self.user.id)
        session.save()

        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id), 'pin': '5678'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify PIN was set
        self.user.refresh_from_db()
        assert self.user.check_pin('5678') is True

    def test_setup_pin_invalid_length(self):
        """PIN must be 4 digits."""
        session = self.client.session
        session['pending_user_id'] = str(self.user.id)
        session.save()

        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id), 'pin': '123'}),  # Only 3 digits
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

    def test_setup_pin_non_numeric(self):
        """PIN must be numeric."""
        session = self.client.session
        session['pending_user_id'] = str(self.user.id)
        session.save()

        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id), 'pin': 'abcd'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

    def test_setup_pin_sets_user_session(self):
        """After setup, user session should be established."""
        session = self.client.session
        session['pending_user_id'] = str(self.user.id)
        session.save()

        response = self.client.post(
            self.url,
            data=json.dumps({'user_id': str(self.user.id), 'pin': '1234'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        # local_user_id should be set after successful setup
        assert self.client.session.get('local_user_id') == str(self.user.id)


class TestLogoutView(TestCase):
    """Test logout functionality."""

    def setUp(self):
        self.client = Client()
        self.url = '/logout/'
        self.user = LocalUser.objects.create(
            email='logout@example.com',
            name='Logout User',
            role='admin',
            pin_hash='',
            is_active=True
        )
        self.user.set_pin('1234')

    def test_logout_clears_session(self):
        """Logout should clear user session."""
        # First login
        session = self.client.session
        session['local_user_id'] = str(self.user.id)
        session['user_email'] = self.user.email
        session.save()

        response = self.client.get(self.url)

        assert response.status_code == 302
        assert 'local_user_id' not in self.client.session

    def test_logout_redirects_to_login(self):
        """Logout should redirect to login page."""
        response = self.client.get(self.url)

        assert response.status_code == 302
        assert '/login/' in response.url or response.url == '/'


class TestEmployeeAPIViews(TestCase):
    """Test employee management API views."""

    def setUp(self):
        self.client = Client()
        self.admin = LocalUser.objects.create(
            email='admin@example.com',
            name='Admin User',
            role='admin',
            pin_hash='',
            is_active=True
        )
        self.admin.set_pin('1234')

        # Login as admin
        session = self.client.session
        session['local_user_id'] = str(self.admin.id)
        session['user_role'] = 'admin'
        session.save()

    def test_create_employee(self):
        """Admin should be able to create employee."""
        response = self.client.post(
            '/api/v1/employees/',
            data=json.dumps({
                'name': 'New Employee',
                'email': 'newemployee@example.com',
                'role': 'employee',
                'pin': '5678'
            }),
            content_type='application/json'
        )

        # DRF returns 201 for successful creation
        assert response.status_code == 201
        data = response.json()
        assert data['name'] == 'New Employee'

        # Verify employee was created
        employee = LocalUser.objects.get(email='newemployee@example.com')
        assert employee.name == 'New Employee'
        assert employee.role == 'employee'

    def test_delete_employee(self):
        """Admin should be able to delete (deactivate) employee."""
        employee = LocalUser.objects.create(
            email='todelete@example.com',
            name='To Delete',
            role='employee',
            pin_hash='',
            is_active=True
        )

        # DRF uses DELETE method on detail endpoint
        response = self.client.delete(
            f'/api/v1/employees/{employee.id}/',
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify employee was deactivated (soft delete)
        employee.refresh_from_db()
        assert employee.is_active is False

    def test_create_employee_duplicate_email(self):
        """Creating employee with existing email should fail."""
        response = self.client.post(
            '/api/v1/employees/',
            data=json.dumps({
                'name': 'Duplicate',
                'email': 'admin@example.com',  # Already exists
                'role': 'employee',
                'pin': '1234'
            }),
            content_type='application/json'
        )

        # DRF returns 400 for validation errors
        assert response.status_code == 400
        data = response.json()
        assert 'email' in data  # Validation error on email field

    def test_reset_employee_pin(self):
        """Admin should be able to reset employee PIN."""
        employee = LocalUser.objects.create(
            email='resetpin@example.com',
            name='Reset PIN',
            role='employee',
            pin_hash='',
            is_active=True
        )
        employee.set_pin('1111')

        # DRF action is at detail endpoint: /api/v1/employees/{id}/reset-pin/
        response = self.client.post(
            f'/api/v1/employees/{employee.id}/reset-pin/',
            data=json.dumps({'pin': '9999'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify PIN was changed
        employee.refresh_from_db()
        assert employee.check_pin('9999') is True
        assert employee.check_pin('1111') is False
