"""
Tests for accounts decorators: login_required, role_required, permission_required, admin_required.
"""
import pytest
from unittest.mock import MagicMock, patch
from django.http import HttpResponse, HttpResponseForbidden
from django.test import RequestFactory

from apps.accounts.decorators import (
    login_required,
    role_required,
    permission_required,
    admin_required,
    _get_current_user,
)
from apps.accounts.models import LocalUser, Role, RolePermission, Permission


@pytest.fixture
def rf():
    """Django RequestFactory."""
    return RequestFactory()


@pytest.fixture
def mock_view():
    """A simple view function for testing decorators."""
    def view(request):
        return HttpResponse("OK")
    return view


class TestLoginRequired:
    """Tests for @login_required decorator."""

    def test_authenticated_user_passes(self, rf, mock_view):
        """Test that authenticated user can access view."""
        request = rf.get('/')
        request.session = {'local_user_id': 'user-123'}

        decorated = login_required(mock_view)
        response = decorated(request)

        assert response.status_code == 200
        assert response.content == b"OK"

    def test_unauthenticated_user_redirected(self, rf, mock_view):
        """Test that unauthenticated user is redirected to login."""
        request = rf.get('/protected/')
        request.session = {}

        decorated = login_required(mock_view)
        response = decorated(request)

        assert response.status_code == 302
        assert 'auth' in response.url or 'login' in response.url

    def test_custom_redirect_url(self, rf, mock_view):
        """Test custom redirect URL."""
        request = rf.get('/protected/')
        request.session = {}

        decorated = login_required(redirect_url='/custom-login/')
        decorated_view = decorated(mock_view)
        response = decorated_view(request)

        assert response.status_code == 302
        assert '/custom-login/' in response.url

    def test_next_parameter_added(self, rf, mock_view):
        """Test that 'next' parameter is added to redirect URL."""
        request = rf.get('/protected/page/')
        request.session = {}

        decorated = login_required(mock_view)
        response = decorated(request)

        assert 'next=' in response.url


class TestRoleRequired:
    """Tests for @role_required decorator."""

    def test_user_with_required_role_passes(self, rf, mock_view):
        """Test that user with required role can access view."""
        request = rf.get('/')
        request.session = {
            'local_user_id': 'user-123',
            'user_role': 'admin'
        }

        decorated = role_required('admin', 'manager')(mock_view)
        response = decorated(request)

        assert response.status_code == 200

    def test_user_without_required_role_forbidden(self, rf, mock_view):
        """Test that user without required role is forbidden."""
        request = rf.get('/')
        request.session = {
            'local_user_id': 'user-123',
            'user_role': 'employee'
        }

        decorated = role_required('admin', 'manager')(mock_view)
        response = decorated(request)

        assert response.status_code == 403

    def test_unauthenticated_user_redirected(self, rf, mock_view):
        """Test that unauthenticated user is redirected."""
        request = rf.get('/')
        request.session = {}

        decorated = role_required('admin')(mock_view)
        response = decorated(request)

        assert response.status_code == 302


class TestGetCurrentUser:
    """Tests for _get_current_user helper."""

    def test_returns_user_when_authenticated(self, rf, db, admin_user):
        """Test that user is returned when session has valid user_id."""
        request = rf.get('/')
        request.session = {'local_user_id': str(admin_user.id)}

        user = _get_current_user(request)

        assert user is not None
        assert user.id == admin_user.id

    def test_returns_none_when_no_session(self, rf):
        """Test that None is returned when no user_id in session."""
        request = rf.get('/')
        request.session = {}

        user = _get_current_user(request)

        assert user is None

    def test_returns_none_when_user_not_found(self, rf, db):
        """Test that None is returned when user doesn't exist."""
        import uuid
        request = rf.get('/')
        request.session = {'local_user_id': str(uuid.uuid4())}  # Valid UUID but nonexistent

        user = _get_current_user(request)

        assert user is None

    def test_returns_none_when_user_inactive(self, rf, db, hub_id):
        """Test that None is returned when user is inactive."""
        inactive_user = LocalUser.objects.create(
            hub_id=hub_id,
            name="Inactive",
            email="inactive@test.com",
            role="employee",
            is_active=False,
        )

        request = rf.get('/')
        request.session = {'local_user_id': str(inactive_user.id)}

        user = _get_current_user(request)

        assert user is None


class TestPermissionRequired:
    """Tests for @permission_required decorator."""

    def test_admin_always_passes(self, rf, db, admin_user, mock_view):
        """Test that admin role bypasses permission check."""
        request = rf.get('/')
        request.session = {
            'local_user_id': str(admin_user.id),
            'user_role': 'admin'
        }

        decorated = permission_required('inventory.view_product')(mock_view)
        response = decorated(request)

        assert response.status_code == 200

    def test_user_with_permission_passes(
        self, rf, db, hub_id, employee_user, role_employee, permission_view_product, mock_view
    ):
        """Test that user with required permission can access view."""
        # Assign permission to role
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_product,
        )
        employee_user.role_obj = role_employee
        employee_user.save()

        request = rf.get('/')
        request.session = {
            'local_user_id': str(employee_user.id),
            'user_role': 'employee'
        }

        decorated = permission_required('inventory.view_product')(mock_view)
        response = decorated(request)

        assert response.status_code == 200

    def test_user_without_permission_forbidden(
        self, rf, db, hub_id, employee_user, role_employee, mock_view
    ):
        """Test that user without required permission is forbidden."""
        employee_user.role_obj = role_employee
        employee_user.save()

        request = rf.get('/')
        request.session = {
            'local_user_id': str(employee_user.id),
            'user_role': 'employee'
        }

        decorated = permission_required('inventory.view_product')(mock_view)
        response = decorated(request)

        assert response.status_code == 403

    def test_multiple_permissions_all_required(
        self, rf, db, hub_id, employee_user, role_employee,
        permission_view_product, permission_add_product, mock_view
    ):
        """Test that all permissions are required by default."""
        # Only assign one permission
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_product,
        )
        employee_user.role_obj = role_employee
        employee_user.save()

        request = rf.get('/')
        request.session = {
            'local_user_id': str(employee_user.id),
            'user_role': 'employee'
        }

        # Require both permissions
        decorated = permission_required(
            'inventory.view_product',
            'inventory.add_product'
        )(mock_view)
        response = decorated(request)

        # Should be forbidden (missing add_product)
        assert response.status_code == 403

    def test_multiple_permissions_any_perm(
        self, rf, db, hub_id, employee_user, role_employee,
        permission_view_product, mock_view
    ):
        """Test any_perm=True allows access with just one permission."""
        # Only assign one permission
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_product,
        )
        employee_user.role_obj = role_employee
        employee_user.save()

        request = rf.get('/')
        request.session = {
            'local_user_id': str(employee_user.id),
            'user_role': 'employee'
        }

        # Require any of the permissions
        decorated = permission_required(
            'inventory.view_product',
            'inventory.add_product',
            any_perm=True
        )(mock_view)
        response = decorated(request)

        # Should pass (has view_product)
        assert response.status_code == 200

    def test_no_permissions_just_login(self, rf, db, employee_user, mock_view):
        """Test that no permissions specified just requires login."""
        request = rf.get('/')
        request.session = {
            'local_user_id': str(employee_user.id),
            'user_role': 'employee'
        }

        decorated = permission_required()(mock_view)
        response = decorated(request)

        assert response.status_code == 200

    def test_unauthenticated_user_redirected(self, rf, mock_view):
        """Test that unauthenticated user is redirected."""
        request = rf.get('/')
        request.session = {}

        decorated = permission_required('inventory.view_product')(mock_view)
        response = decorated(request)

        assert response.status_code == 302


class TestAdminRequired:
    """Tests for @admin_required decorator."""

    def test_admin_user_passes(self, rf, db, admin_user, mock_view):
        """Test that admin user can access view."""
        request = rf.get('/')
        request.session = {
            'local_user_id': str(admin_user.id),
            'user_role': 'admin'
        }

        decorated = admin_required(mock_view)
        response = decorated(request)

        assert response.status_code == 200

    def test_non_admin_forbidden(self, rf, db, employee_user, mock_view):
        """Test that non-admin user is forbidden."""
        request = rf.get('/')
        request.session = {
            'local_user_id': str(employee_user.id),
            'user_role': 'employee'
        }

        decorated = admin_required(mock_view)
        response = decorated(request)

        assert response.status_code == 403

    def test_unauthenticated_redirected(self, rf, mock_view):
        """Test that unauthenticated user is redirected."""
        request = rf.get('/')
        request.session = {}

        decorated = admin_required(mock_view)
        response = decorated(request)

        assert response.status_code == 302
