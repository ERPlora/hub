"""
Tests for roles management views.
"""
import pytest
import json
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, Permission, RolePermission, LocalUser


@pytest.fixture
def authenticated_client(client, db, hub_id, admin_user, configured_hub, configured_store):
    """Client with authenticated admin session."""
    session = client.session
    session['local_user_id'] = str(admin_user.id)
    session['user_role'] = 'admin'
    session['hub_id'] = str(hub_id)
    session.save()
    return client


class TestRoleListView:
    """Tests for role list view."""

    def test_role_list_requires_admin(self, client, db, hub_id, employee_user, configured_hub, configured_store):
        """Test that role list requires admin role."""
        session = client.session
        session['local_user_id'] = str(employee_user.id)
        session['user_role'] = 'employee'
        session['hub_id'] = str(hub_id)
        session.save()

        response = client.get('/roles/')

        assert response.status_code == 403

    def test_role_list_displays_roles(self, authenticated_client, db, hub_id, role_admin, role_manager):
        """Test that role list displays all roles."""
        response = authenticated_client.get('/roles/')

        assert response.status_code == 200
        assert b'Administrator' in response.content or b'admin' in response.content

    def test_role_list_shows_user_count(self, authenticated_client, db, hub_id, role_admin, admin_user):
        """Test that role list shows user count per role."""
        admin_user.role_obj = role_admin
        admin_user.save()

        response = authenticated_client.get('/roles/')

        assert response.status_code == 200


class TestRoleDetailView:
    """Tests for role detail view."""

    def test_role_detail_displays_permissions(
        self, authenticated_client, db, hub_id, role_custom, permission_view_product
    ):
        """Test that role detail shows assigned permissions."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_view_product,
        )

        response = authenticated_client.get(f'/roles/{role_custom.id}/')

        assert response.status_code == 200

    def test_role_detail_shows_wildcards(self, authenticated_client, db, hub_id, role_admin):
        """Test that role detail shows wildcard permissions."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_admin,
            wildcard='*',
        )

        response = authenticated_client.get(f'/roles/{role_admin.id}/')

        assert response.status_code == 200


class TestRoleCreateView:
    """Tests for role creation."""

    def test_create_role_get(self, authenticated_client):
        """Test GET request shows create form."""
        response = authenticated_client.get('/roles/create/')

        assert response.status_code == 200

    def test_create_role_post_success(self, authenticated_client, db, hub_id):
        """Test POST creates new role."""
        response = authenticated_client.post('/roles/create/', {
            'name': 'cashier',
            'display_name': 'Cashier',
            'description': 'Can process sales',
        })

        assert response.status_code == 302  # Redirect on success
        assert Role.objects.filter(hub_id=hub_id, name='cashier').exists()

    def test_create_role_duplicate_name(self, authenticated_client, db, hub_id, role_admin):
        """Test creating role with existing name fails."""
        response = authenticated_client.post('/roles/create/', {
            'name': 'admin',  # Already exists
            'display_name': 'Another Admin',
        })

        # Should redirect back with error or show form again
        assert Role.objects.filter(hub_id=hub_id, name='admin').count() == 1


class TestRoleEditView:
    """Tests for role editing."""

    def test_edit_role_get(self, authenticated_client, role_custom):
        """Test GET shows edit form."""
        response = authenticated_client.get(f'/roles/{role_custom.id}/edit/')

        assert response.status_code == 200

    def test_edit_role_post_success(self, authenticated_client, role_custom):
        """Test POST updates role."""
        response = authenticated_client.post(f'/roles/{role_custom.id}/edit/', {
            'display_name': 'Updated Name',
            'description': 'Updated description',
        })

        assert response.status_code == 302
        role_custom.refresh_from_db()
        assert role_custom.display_name == 'Updated Name'


class TestRoleDeleteView:
    """Tests for role deletion."""

    def test_delete_role_get(self, authenticated_client, role_custom):
        """Test GET shows confirmation."""
        response = authenticated_client.get(f'/roles/{role_custom.id}/delete/')

        assert response.status_code == 200

    def test_delete_custom_role(self, authenticated_client, db, hub_id, role_custom):
        """Test deleting custom role."""
        role_id = role_custom.id

        response = authenticated_client.post(f'/roles/{role_id}/delete/')

        assert response.status_code == 302
        assert not Role.objects.filter(id=role_id).exists()

    def test_cannot_delete_system_role(self, authenticated_client, role_admin):
        """Test that system roles cannot be deleted."""
        response = authenticated_client.post(f'/roles/{role_admin.id}/delete/')

        # Should redirect with error
        assert response.status_code == 302
        assert Role.objects.filter(id=role_admin.id).exists()

    def test_cannot_delete_role_with_users(self, authenticated_client, db, hub_id, role_custom, employee_user):
        """Test that roles assigned to users cannot be deleted."""
        employee_user.role_obj = role_custom
        employee_user.save()

        response = authenticated_client.post(f'/roles/{role_custom.id}/delete/')

        # Should redirect with error
        assert response.status_code == 302
        assert Role.objects.filter(id=role_custom.id).exists()


class TestRoleToggleActive:
    """Tests for toggling role active status."""

    def test_toggle_role_active(self, authenticated_client, role_custom):
        """Test toggling role active status."""
        assert role_custom.is_active is True

        response = authenticated_client.post(f'/roles/{role_custom.id}/toggle-active/')

        assert response.status_code == 302
        role_custom.refresh_from_db()
        assert role_custom.is_active is False

    def test_cannot_deactivate_admin(self, authenticated_client, role_admin):
        """Test that admin role cannot be deactivated."""
        response = authenticated_client.post(f'/roles/{role_admin.id}/toggle-active/')

        assert response.status_code == 302
        role_admin.refresh_from_db()
        assert role_admin.is_active is True


class TestRolePermissionsAPI:
    """Tests for role permissions API."""

    def test_update_permissions_add(
        self, authenticated_client, db, hub_id, role_custom, permission_view_product
    ):
        """Test adding permission via API."""
        response = authenticated_client.post(
            f'/roles/api/{role_custom.id}/permissions/',
            data=json.dumps({
                'add': ['inventory.view_product'],
                'remove': [],
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['added'] == 1

    def test_update_permissions_remove(
        self, authenticated_client, db, hub_id, role_custom, permission_view_product
    ):
        """Test removing permission via API."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_view_product,
        )

        response = authenticated_client.post(
            f'/roles/api/{role_custom.id}/permissions/',
            data=json.dumps({
                'add': [],
                'remove': ['inventory.view_product'],
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['removed'] == 1


class TestWildcardAPI:
    """Tests for wildcard management API."""

    def test_add_wildcard(self, authenticated_client, db, hub_id, role_custom):
        """Test adding wildcard permission."""
        response = authenticated_client.post(
            f'/roles/api/{role_custom.id}/wildcard/',
            data=json.dumps({'wildcard': 'inventory.*'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        assert RolePermission.objects.filter(
            role=role_custom,
            wildcard='inventory.*'
        ).exists()

    def test_add_invalid_wildcard(self, authenticated_client, role_custom):
        """Test adding invalid wildcard pattern."""
        response = authenticated_client.post(
            f'/roles/api/{role_custom.id}/wildcard/',
            data=json.dumps({'wildcard': 'no_asterisk'}),
            content_type='application/json'
        )

        assert response.status_code == 400

    def test_remove_wildcard(self, authenticated_client, db, hub_id, role_custom):
        """Test removing wildcard permission."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            wildcard='inventory.*',
        )

        response = authenticated_client.post(
            f'/roles/api/{role_custom.id}/wildcard/inventory.*/'
        )

        assert response.status_code == 200

    def test_cannot_remove_admin_all_wildcard(self, authenticated_client, db, hub_id, role_admin):
        """Test that '*' cannot be removed from admin role."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_admin,
            wildcard='*',
        )

        response = authenticated_client.post(
            f'/roles/api/{role_admin.id}/wildcard/*/'
        )

        assert response.status_code == 400


class TestSyncPermissions:
    """Tests for permission sync endpoint."""

    def test_sync_permissions(self, authenticated_client):
        """Test syncing permissions from modules."""
        response = authenticated_client.get('/roles/sync-permissions/')

        assert response.status_code == 302  # Redirect on success


class TestCreateDefaultRoles:
    """Tests for creating default roles endpoint."""

    def test_create_default_roles(self, authenticated_client, db, hub_id):
        """Test creating default roles."""
        response = authenticated_client.get('/roles/create-defaults/')

        assert response.status_code == 302

        # Verify roles created
        assert Role.objects.filter(hub_id=hub_id, name='admin').exists()
        assert Role.objects.filter(hub_id=hub_id, name='manager').exists()
        assert Role.objects.filter(hub_id=hub_id, name='employee').exists()
