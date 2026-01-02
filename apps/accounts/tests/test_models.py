"""
Tests for accounts models: Permission, Role, RolePermission, LocalUser permissions.
"""
import pytest
from django.db import IntegrityError

from apps.accounts.models import Permission, Role, RolePermission, LocalUser


class TestPermissionModel:
    """Tests for Permission model."""

    def test_permission_creation(self, db, hub_id):
        """Test creating a permission."""
        perm = Permission.objects.create(
            hub_id=hub_id,
            codename="inventory.view_product",
            name="Can view product",
            module_id="inventory",
        )

        assert perm.pk is not None
        assert perm.codename == "inventory.view_product"
        assert perm.name == "Can view product"
        assert perm.module_id == "inventory"
        assert perm.is_deleted is False

    def test_permission_str(self, permission_view_product):
        """Test permission string representation."""
        # Format: "codename: name"
        result = str(permission_view_product)
        assert "inventory.view_product" in result
        assert "Can view product" in result

    def test_permission_unique_constraint(self, db, hub_id, permission_view_product):
        """Test that codename must be unique per hub."""
        with pytest.raises(IntegrityError):
            Permission.objects.create(
                hub_id=hub_id,
                codename="inventory.view_product",  # Same codename
                name="Duplicate permission",
                module_id="inventory",
            )

    def test_permission_soft_delete(self, permission_view_product):
        """Test soft delete on permission."""
        perm_id = permission_view_product.pk
        permission_view_product.soft_delete()

        # Should not be found with default manager
        assert not Permission.objects.filter(pk=perm_id).exists()

        # Should be found with all_objects manager
        deleted_perm = Permission.all_objects.get(pk=perm_id)
        assert deleted_perm.is_deleted is True
        assert deleted_perm.deleted_at is not None


class TestRoleModel:
    """Tests for Role model."""

    def test_role_creation(self, db, hub_id):
        """Test creating a role."""
        role = Role.objects.create(
            hub_id=hub_id,
            name="supervisor",
            display_name="Supervisor",
            description="Can supervise employees",
            is_system=False,
            is_active=True,
        )

        assert role.pk is not None
        assert role.name == "supervisor"
        assert role.display_name == "Supervisor"
        assert role.description == "Can supervise employees"
        assert role.is_system is False
        assert role.is_active is True

    def test_role_str(self, role_admin):
        """Test role string representation."""
        assert str(role_admin) == "Administrator"

    def test_system_role_flag(self, role_admin, role_custom):
        """Test system role vs custom role."""
        assert role_admin.is_system is True
        assert role_custom.is_system is False

    def test_role_unique_name_per_hub(self, db, hub_id, role_admin):
        """Test that role name must be unique per hub."""
        with pytest.raises(IntegrityError):
            Role.objects.create(
                hub_id=hub_id,
                name="admin",  # Same name
                display_name="Another Admin",
                description="Another admin",
                is_system=False,
            )

    def test_role_soft_delete(self, role_custom):
        """Test soft delete on role."""
        role_id = role_custom.pk
        role_custom.soft_delete()

        assert not Role.objects.filter(pk=role_id).exists()
        assert Role.all_objects.filter(pk=role_id).exists()


class TestRolePermissionModel:
    """Tests for RolePermission (M2M through) model."""

    def test_assign_permission_to_role(
        self, db, hub_id, role_custom, permission_view_product
    ):
        """Test assigning a permission to a role."""
        role_perm = RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_view_product,
        )

        assert role_perm.pk is not None
        assert role_perm.role == role_custom
        assert role_perm.permission == permission_view_product

    def test_role_permissions_m2m(
        self, db, hub_id, role_custom, permission_view_product, permission_add_product
    ):
        """Test M2M relationship between Role and Permission."""
        # Add permissions to role
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_view_product,
        )
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_add_product,
        )

        # Check via M2M
        assert role_custom.permissions.count() == 2
        assert permission_view_product in role_custom.permissions.all()
        assert permission_add_product in role_custom.permissions.all()

    def test_permission_roles_reverse_m2m(
        self, db, hub_id, role_custom, role_manager, permission_view_product
    ):
        """Test reverse M2M from Permission to Roles."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_view_product,
        )
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_manager,
            permission=permission_view_product,
        )

        # Check reverse relationship
        assert permission_view_product.roles.count() == 2
        assert role_custom in permission_view_product.roles.all()
        assert role_manager in permission_view_product.roles.all()

    def test_unique_role_permission(
        self, db, hub_id, role_custom, permission_view_product
    ):
        """Test that same permission can't be assigned twice to same role."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_custom,
            permission=permission_view_product,
        )

        with pytest.raises(IntegrityError):
            RolePermission.objects.create(
                hub_id=hub_id,
                role=role_custom,
                permission=permission_view_product,
            )


class TestLocalUserPermissions:
    """Tests for LocalUser permission methods."""

    def test_get_permissions_empty(self, employee_user):
        """Test get_permissions with no role_obj assigned."""
        perms = employee_user.get_permissions()
        assert perms == set()

    def test_get_permissions_with_role(
        self, db, hub_id, employee_user, role_employee, permission_view_product, permission_view_sale
    ):
        """Test get_permissions with role_obj assigned."""
        # Assign permissions to role
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_product,
        )
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_sale,
        )

        # Assign role to user
        employee_user.role_obj = role_employee
        employee_user.save()

        perms = employee_user.get_permissions()
        assert "inventory.view_product" in perms
        assert "sales.view_sale" in perms
        assert len(perms) == 2

    def test_get_permissions_with_extra(
        self, db, hub_id, employee_user, role_employee, permission_view_product, permission_add_product
    ):
        """Test get_permissions includes extra_permissions."""
        # Assign one permission to role
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_product,
        )
        employee_user.role_obj = role_employee

        # Add extra permission directly to user
        employee_user.extra_permissions.add(permission_add_product)
        employee_user.save()

        perms = employee_user.get_permissions()
        assert "inventory.view_product" in perms  # From role
        assert "inventory.add_product" in perms   # From extra
        assert len(perms) == 2

    def test_has_perm_admin_always_true(self, admin_user):
        """Test that admin role always returns True for has_perm."""
        assert admin_user.has_perm("any.permission") is True
        assert admin_user.has_perm("nonexistent.permission") is True

    def test_has_perm_with_permission(
        self, db, hub_id, employee_user, role_employee, permission_view_product
    ):
        """Test has_perm returns True when user has the permission."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_product,
        )
        employee_user.role_obj = role_employee
        employee_user.save()

        assert employee_user.has_perm("inventory.view_product") is True

    def test_has_perm_without_permission(
        self, db, hub_id, employee_user, role_employee, permission_view_product
    ):
        """Test has_perm returns False when user lacks the permission."""
        # Role has view_product but user checking for add_product
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_product,
        )
        employee_user.role_obj = role_employee
        employee_user.save()

        assert employee_user.has_perm("inventory.add_product") is False

    def test_has_module_perms_admin(self, admin_user):
        """Test has_module_perms for admin."""
        assert admin_user.has_module_perms("inventory") is True
        assert admin_user.has_module_perms("any_module") is True

    def test_has_module_perms_with_permission(
        self, db, hub_id, employee_user, role_employee, permission_view_product
    ):
        """Test has_module_perms returns True when user has any perm in module."""
        RolePermission.objects.create(
            hub_id=hub_id,
            role=role_employee,
            permission=permission_view_product,
        )
        employee_user.role_obj = role_employee
        employee_user.save()

        assert employee_user.has_module_perms("inventory") is True
        assert employee_user.has_module_perms("sales") is False

    def test_get_role_name_with_role_obj(
        self, db, hub_id, employee_user, role_employee
    ):
        """Test get_role_name with role_obj assigned."""
        employee_user.role_obj = role_employee
        employee_user.save()

        assert employee_user.get_role_name() == "employee"

    def test_get_role_name_fallback_to_legacy(self, employee_user):
        """Test get_role_name falls back to legacy role field."""
        # No role_obj, should use legacy field
        assert employee_user.role_obj is None
        assert employee_user.get_role_name() == "employee"

    def test_get_role_color(self, admin_user, manager_user, employee_user):
        """Test get_role_color returns correct colors."""
        # Without role_obj, uses legacy role field colors
        assert admin_user.get_role_color() == "primary"
        assert manager_user.get_role_color() == "tertiary"
        assert employee_user.get_role_color() == "success"
