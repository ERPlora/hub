"""
Tests for PermissionService.
"""
import pytest
from unittest.mock import patch, MagicMock

from apps.accounts.models import Permission, Role, RolePermission
from apps.core.services.permission_service import PermissionService


class TestExpandWildcard:
    """Tests for wildcard expansion."""

    def test_expand_wildcard_all(self, db, hub_id):
        """Test '*' wildcard matches all permissions."""
        # Create some permissions
        Permission.objects.create(
            hub_id=hub_id, codename='inventory.view_product',
            name='View product', module_id='inventory'
        )
        Permission.objects.create(
            hub_id=hub_id, codename='sales.add_sale',
            name='Add sale', module_id='sales'
        )

        all_codenames = ['inventory.view_product', 'sales.add_sale']
        result = PermissionService.expand_wildcard('*', all_codenames)

        assert 'inventory.view_product' in result
        assert 'sales.add_sale' in result
        assert len(result) == 2

    def test_expand_module_wildcard(self, db, hub_id):
        """Test 'module.*' wildcard matches all module permissions."""
        all_codenames = [
            'inventory.view_product',
            'inventory.add_product',
            'sales.view_sale'
        ]

        result = PermissionService.expand_wildcard('inventory.*', all_codenames)

        assert 'inventory.view_product' in result
        assert 'inventory.add_product' in result
        assert 'sales.view_sale' not in result
        assert len(result) == 2

    def test_expand_action_wildcard(self, db, hub_id):
        """Test 'module.action_*' wildcard matches action permissions."""
        all_codenames = [
            'inventory.view_product',
            'inventory.view_category',
            'inventory.add_product',
        ]

        result = PermissionService.expand_wildcard('inventory.view_*', all_codenames)

        assert 'inventory.view_product' in result
        assert 'inventory.view_category' in result
        assert 'inventory.add_product' not in result
        assert len(result) == 2


class TestExpandRolePermissions:
    """Tests for expanding role permissions."""

    def test_expand_direct_permissions(self, db, hub_id, role_custom, permission_view_product):
        """Test direct permission assignment."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_view_product,
        )

        result = PermissionService.expand_role_permissions(role_custom)

        assert 'inventory.view_product' in result
        assert len(result) == 1

    def test_expand_wildcard_permissions(self, db, hub_id, role_custom):
        """Test wildcard permission expansion."""
        # Create permissions
        Permission.objects.create(
            hub_id=hub_id, codename='inventory.view_product',
            name='View product', module_id='inventory'
        )
        Permission.objects.create(
            hub_id=hub_id, codename='inventory.add_product',
            name='Add product', module_id='inventory'
        )
        Permission.objects.create(
            hub_id=hub_id, codename='sales.view_sale',
            name='View sale', module_id='sales'
        )

        # Assign wildcard
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            wildcard='inventory.*',
        )

        result = PermissionService.expand_role_permissions(role_custom)

        assert 'inventory.view_product' in result
        assert 'inventory.add_product' in result
        assert 'sales.view_sale' not in result

    def test_expand_mixed_permissions(self, db, hub_id, role_custom, permission_view_sale):
        """Test mixed direct and wildcard permissions."""
        # Create inventory permissions
        Permission.objects.create(
            hub_id=hub_id, codename='inventory.view_product',
            name='View product', module_id='inventory'
        )

        # Direct permission for sales
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_view_sale,
        )

        # Wildcard for inventory
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            wildcard='inventory.*',
        )

        result = PermissionService.expand_role_permissions(role_custom)

        assert 'inventory.view_product' in result  # From wildcard
        assert 'sales.view_sale' in result  # From direct


class TestSyncModulePermissions:
    """Tests for syncing module permissions."""

    def test_sync_creates_permissions(self, db, hub_id):
        """Test that sync creates new permissions."""
        permissions = [
            ('view_product', 'Can view product'),
            ('add_product', 'Can add product'),
        ]

        count = PermissionService.sync_module_permissions(
            hub_id=str(hub_id),
            module_id='inventory',
            permissions=permissions
        )

        assert count == 2
        assert Permission.objects.filter(
            hub_id=hub_id,
            codename='inventory.view_product'
        ).exists()
        assert Permission.objects.filter(
            hub_id=hub_id,
            codename='inventory.add_product'
        ).exists()

    def test_sync_with_description(self, db, hub_id):
        """Test sync with permission descriptions."""
        permissions = [
            ('view_product', 'Can view product', 'Allows viewing product details'),
        ]

        PermissionService.sync_module_permissions(
            hub_id=str(hub_id),
            module_id='inventory',
            permissions=permissions
        )

        perm = Permission.objects.get(hub_id=hub_id, codename='inventory.view_product')
        assert perm.description == 'Allows viewing product details'

    def test_sync_updates_existing(self, db, hub_id):
        """Test that sync updates existing permissions."""
        # Create existing permission
        Permission.objects.create(
            hub_id=hub_id,
            codename='inventory.view_product',
            name='Old name',
            module_id='inventory',
        )

        permissions = [
            ('view_product', 'New name'),
        ]

        PermissionService.sync_module_permissions(
            hub_id=str(hub_id),
            module_id='inventory',
            permissions=permissions
        )

        perm = Permission.objects.get(hub_id=hub_id, codename='inventory.view_product')
        assert perm.name == 'New name'


class TestCreateDefaultRoles:
    """Tests for creating default roles."""

    def test_creates_default_roles(self, db, hub_id):
        """Test that default roles are created."""
        roles = PermissionService.create_default_roles(str(hub_id))

        assert len(roles) == 4  # admin, manager, employee, viewer

        # Verify admin role
        admin = Role.objects.get(hub_id=hub_id, name='admin')
        assert admin.is_system is True
        assert admin.display_name == 'Administrator'

        # Verify manager role
        manager = Role.objects.get(hub_id=hub_id, name='manager')
        assert manager.is_system is True

        # Verify employee role
        employee = Role.objects.get(hub_id=hub_id, name='employee')
        assert employee.is_system is True

        # Verify viewer role
        viewer = Role.objects.get(hub_id=hub_id, name='viewer')
        assert viewer.is_system is True

    def test_admin_has_all_wildcard(self, db, hub_id):
        """Test that admin role gets '*' wildcard."""
        PermissionService.create_default_roles(str(hub_id))

        admin = Role.objects.get(hub_id=hub_id, name='admin')

        # Should have '*' wildcard
        assert RolePermission.objects.filter(
            role=admin,
            wildcard='*',
            is_deleted=False
        ).exists()

    def test_skips_existing_roles(self, db, hub_id):
        """Test that existing roles are not duplicated."""
        # Pre-create admin role
        Role.objects.create(
            hub_id=hub_id,
            name='admin',
            display_name='Existing Admin',
            is_system=True,
        )

        roles = PermissionService.create_default_roles(str(hub_id))

        # Should still return 4 roles (including existing)
        assert len(roles) == 4

        # Only one admin should exist
        assert Role.objects.filter(hub_id=hub_id, name='admin').count() == 1


class TestAssignRoleToUser:
    """Tests for assigning roles to users."""

    def test_assign_role_updates_both_fields(self, db, hub_id, employee_user, role_manager):
        """Test that assigning role updates both role_obj and legacy role field."""
        PermissionService.assign_role_to_user(employee_user, role_manager)

        employee_user.refresh_from_db()
        assert employee_user.role_obj == role_manager
        assert employee_user.role == 'manager'


class TestExtraPermissions:
    """Tests for extra permission management."""

    def test_add_extra_permission(self, db, employee_user, permission_view_product):
        """Test adding extra permission to user."""
        result = PermissionService.add_extra_permission(employee_user, permission_view_product)

        assert result is True
        assert permission_view_product in employee_user.extra_permissions.all()

    def test_add_extra_permission_already_exists(self, db, employee_user, permission_view_product):
        """Test adding permission that user already has."""
        employee_user.extra_permissions.add(permission_view_product)

        result = PermissionService.add_extra_permission(employee_user, permission_view_product)

        assert result is False

    def test_remove_extra_permission(self, db, employee_user, permission_view_product):
        """Test removing extra permission from user."""
        employee_user.extra_permissions.add(permission_view_product)

        result = PermissionService.remove_extra_permission(employee_user, permission_view_product)

        assert result is True
        assert permission_view_product not in employee_user.extra_permissions.all()

    def test_remove_extra_permission_not_exists(self, db, employee_user, permission_view_product):
        """Test removing permission user doesn't have."""
        result = PermissionService.remove_extra_permission(employee_user, permission_view_product)

        assert result is False
