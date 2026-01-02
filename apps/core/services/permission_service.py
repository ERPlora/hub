"""
Permission Service for Hub.

Handles:
- Syncing permissions from module PERMISSIONS lists to database
- Creating default roles (admin, manager, employee)
- Expanding wildcard patterns in role permissions
"""

import fnmatch
import logging
from typing import List, Set

from django.db import transaction

logger = logging.getLogger(__name__)


class PermissionService:
    """
    Service for managing permissions and roles.

    Permissions are defined in each module's module.py file:

        PERMISSIONS = [
            ('view_product', 'Can view products'),
            ('add_product', 'Can add products'),
            ('change_product', 'Can edit products'),
            ('delete_product', 'Can delete products'),
        ]

    These are synced to the Permission model with codenames like:
        'inventory.view_product', 'inventory.add_product', etc.
    """

    # Default roles configuration
    DEFAULT_ROLES = [
        {
            'name': 'admin',
            'display_name': 'Administrator',
            'description': 'Full system access. Can manage all settings, users, and data.',
            'is_system': True,
            'wildcards': ['*'],  # All permissions
        },
        {
            'name': 'manager',
            'display_name': 'Manager',
            'description': 'Management access. Can view reports, manage inventory, and process sales.',
            'is_system': True,
            'wildcards': [
                'inventory.*',
                'sales.*',
                'customers.*',
                'cash_register.*',
            ],
        },
        {
            'name': 'employee',
            'display_name': 'Employee',
            'description': 'Basic access. Can process sales and view products.',
            'is_system': True,
            'wildcards': [
                'inventory.view_*',
                'sales.view_*',
                'sales.add_sale',
                'sales.process_payment',
                'customers.view_*',
            ],
        },
    ]

    @classmethod
    def sync_module_permissions(cls, hub_id: str, module_id: str, permissions: List[tuple]) -> int:
        """
        Sync permissions from a module's PERMISSIONS list to the database.

        Args:
            hub_id: Hub UUID
            module_id: Module identifier (e.g., 'inventory')
            permissions: List of (codename, name) or (codename, name, description) tuples

        Returns:
            Number of permissions created/updated
        """
        from apps.accounts.models import Permission

        count = 0

        for perm_tuple in permissions:
            if len(perm_tuple) == 2:
                codename_suffix, name = perm_tuple
                description = ''
            else:
                codename_suffix, name, description = perm_tuple[:3]

            # Full codename includes module prefix
            codename = f"{module_id}.{codename_suffix}"

            # Create or update permission
            perm, created = Permission.objects.update_or_create(
                hub_id=hub_id,
                codename=codename,
                defaults={
                    'name': name,
                    'description': description,
                    'module_id': module_id,
                }
            )

            if created:
                logger.debug(f"Created permission: {codename}")
            count += 1

        return count

    @classmethod
    def sync_all_module_permissions(cls, hub_id: str) -> int:
        """
        Sync permissions from all active modules.

        Scans INSTALLED_APPS for modules with PERMISSIONS defined.

        Args:
            hub_id: Hub UUID

        Returns:
            Total number of permissions synced
        """
        from django.conf import settings
        from importlib import import_module

        total = 0

        for app in settings.INSTALLED_APPS:
            # Only process module apps
            if not app.startswith('modules.'):
                continue

            module_id = app.split('.')[-1]

            try:
                # Try to import module.py from the module
                module_path = f"{app}.module"
                mod = import_module(module_path)

                if hasattr(mod, 'PERMISSIONS'):
                    count = cls.sync_module_permissions(
                        hub_id=hub_id,
                        module_id=module_id,
                        permissions=mod.PERMISSIONS
                    )
                    total += count
                    logger.info(f"Synced {count} permissions from {module_id}")

            except ImportError:
                # Module doesn't have module.py or PERMISSIONS
                pass
            except Exception as e:
                logger.warning(f"Error syncing permissions from {module_id}: {e}")

        return total

    @classmethod
    @transaction.atomic
    def create_default_roles(cls, hub_id: str) -> List:
        """
        Create default system roles for a Hub.

        Creates admin, manager, and employee roles with their default
        wildcard permissions.

        Args:
            hub_id: Hub UUID

        Returns:
            List of created/updated Role instances
        """
        from apps.accounts.models import Role, RolePermission

        roles = []

        for role_config in cls.DEFAULT_ROLES:
            # Create or update role
            role, created = Role.objects.update_or_create(
                hub_id=hub_id,
                name=role_config['name'],
                defaults={
                    'display_name': role_config['display_name'],
                    'description': role_config['description'],
                    'is_system': role_config['is_system'],
                }
            )

            if created:
                logger.info(f"Created role: {role.name}")

            # Add wildcard permissions
            for wildcard in role_config.get('wildcards', []):
                RolePermission.objects.get_or_create(
                    hub_id=hub_id,
                    role=role,
                    wildcard=wildcard,
                    defaults={'permission': None}
                )

            roles.append(role)

        return roles

    @classmethod
    def expand_role_permissions(cls, role) -> Set[str]:
        """
        Expand all permissions for a role, including wildcard patterns.

        Args:
            role: Role instance

        Returns:
            Set of permission codenames
        """
        from apps.accounts.models import Permission

        permissions = set()
        hub_id = role.hub_id

        # Get all permissions for this hub (for wildcard expansion)
        all_perms = list(
            Permission.objects.filter(hub_id=hub_id, is_deleted=False)
            .values_list('codename', flat=True)
        )

        # Process each role permission
        for rp in role.role_permissions.filter(is_deleted=False):
            if rp.permission:
                # Direct permission
                permissions.add(rp.permission.codename)
            elif rp.wildcard:
                # Expand wildcard
                expanded = cls.expand_wildcard(rp.wildcard, all_perms)
                permissions.update(expanded)

        return permissions

    @classmethod
    def expand_wildcard(cls, pattern: str, all_codenames: List[str]) -> Set[str]:
        """
        Expand a wildcard pattern to matching permission codenames.

        Supports:
        - '*' = all permissions
        - 'module.*' = all permissions for module
        - 'module.action_*' = matching permissions

        Args:
            pattern: Wildcard pattern
            all_codenames: List of all permission codenames

        Returns:
            Set of matching codenames
        """
        if pattern == '*':
            return set(all_codenames)

        # Use fnmatch for glob-style matching
        return {
            codename for codename in all_codenames
            if fnmatch.fnmatch(codename, pattern)
        }

    @classmethod
    def get_module_permissions(cls, hub_id: str, module_id: str) -> List:
        """
        Get all permissions for a specific module.

        Args:
            hub_id: Hub UUID
            module_id: Module identifier

        Returns:
            List of Permission instances
        """
        from apps.accounts.models import Permission

        return list(
            Permission.objects.filter(
                hub_id=hub_id,
                module_id=module_id,
                is_deleted=False
            ).order_by('codename')
        )

    @classmethod
    def get_permissions_by_module(cls, hub_id: str) -> dict:
        """
        Get all permissions grouped by module.

        Args:
            hub_id: Hub UUID

        Returns:
            Dict mapping module_id to list of permissions
        """
        from apps.accounts.models import Permission
        from collections import defaultdict

        permissions = defaultdict(list)

        for perm in Permission.objects.filter(hub_id=hub_id, is_deleted=False):
            permissions[perm.module_id].append({
                'id': str(perm.id),
                'codename': perm.codename,
                'name': perm.name,
                'description': perm.description,
            })

        return dict(permissions)

    @classmethod
    def assign_role_to_user(cls, user, role) -> None:
        """
        Assign a role to a user.

        Args:
            user: LocalUser instance
            role: Role instance
        """
        user.role_obj = role
        # Also update legacy role field for backwards compatibility
        user.role = role.name
        user.save(update_fields=['role_obj', 'role', 'updated_at'])

    @classmethod
    def add_extra_permission(cls, user, permission) -> bool:
        """
        Add an extra permission to a user.

        Args:
            user: LocalUser instance
            permission: Permission instance

        Returns:
            True if added, False if already had
        """
        if permission in user.extra_permissions.all():
            return False

        user.extra_permissions.add(permission)
        return True

    @classmethod
    def remove_extra_permission(cls, user, permission) -> bool:
        """
        Remove an extra permission from a user.

        Args:
            user: LocalUser instance
            permission: Permission instance

        Returns:
            True if removed, False if didn't have
        """
        if permission not in user.extra_permissions.all():
            return False

        user.extra_permissions.remove(permission)
        return True
