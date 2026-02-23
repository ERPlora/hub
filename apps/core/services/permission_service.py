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

    # Basic roles — always created, always active, not tied to any solution
    DEFAULT_ROLES = [
        {
            'name': 'admin',
            'display_name': 'Administrator',
            'description': 'Full system access. Can manage all settings, users, and data.',
            'is_system': True,
            'wildcards': ['*'],
        },
        {
            'name': 'manager',
            'display_name': 'Manager',
            'description': 'Management access. CRUD on main modules, reports, and team oversight.',
            'is_system': True,
            'wildcards': [
                'inventory.*',
                'sales.*',
                'customers.*',
                'cash_register.*',
                'invoicing.*',
                'reports.*',
            ],
        },
        {
            'name': 'employee',
            'display_name': 'Employee',
            'description': 'Basic access. Day-to-day operations like sales and viewing products.',
            'is_system': True,
            'wildcards': [
                'inventory.view_*',
                'sales.view_*',
                'sales.add_sale',
                'sales.process_payment',
                'customers.view_*',
            ],
        },
        {
            'name': 'viewer',
            'display_name': 'Viewer',
            'description': 'Read-only access. Can view all data but cannot create, edit, or delete anything.',
            'is_system': True,
            'wildcards': [
                '*.view_*',
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

        for perm_entry in permissions:
            if isinstance(perm_entry, str):
                # String format: 'module.codename_suffix' or just 'codename_suffix'
                if '.' in perm_entry:
                    codename = perm_entry
                    codename_suffix = perm_entry.split('.', 1)[1]
                else:
                    codename_suffix = perm_entry
                    codename = f"{module_id}.{codename_suffix}"
                name = codename_suffix.replace('_', ' ').title()
                description = ''
            elif len(perm_entry) == 2:
                codename_suffix, name = perm_entry
                description = ''
                codename = f"{module_id}.{codename_suffix}"
            else:
                codename_suffix, name, description = perm_entry[:3]
                codename = f"{module_id}.{codename_suffix}"

            # Create or update permission
            perm, created = Permission.objects.update_or_create(
                hub_id=hub_id,
                codename=codename,
                defaults={
                    'name': str(name),  # Convert lazy string
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

        Uses the dynamic ModuleLoader to find loaded modules.
        Also applies ROLE_PERMISSIONS defaults for each module.

        Args:
            hub_id: Hub UUID

        Returns:
            Total number of permissions synced
        """
        from apps.modules_runtime.loader import module_loader
        from importlib import import_module

        total = 0

        # Get all loaded modules from the dynamic loader
        for module_id, module_info in module_loader.loaded_modules.items():
            try:
                # Import module.py from the module
                mod = import_module(f"{module_id}.module")

                if hasattr(mod, 'PERMISSIONS'):
                    count = cls.sync_module_permissions(
                        hub_id=hub_id,
                        module_id=module_id,
                        permissions=mod.PERMISSIONS
                    )
                    total += count
                    logger.info(f"Synced {count} permissions from {module_id}")

                    # Apply ROLE_PERMISSIONS defaults if defined
                    if hasattr(mod, 'ROLE_PERMISSIONS'):
                        cls.apply_module_role_defaults(
                            hub_id=hub_id,
                            module_id=module_id,
                            role_permissions=mod.ROLE_PERMISSIONS
                        )

            except ImportError:
                # Module doesn't have module.py or PERMISSIONS
                pass
            except Exception as e:
                logger.warning(f"Error syncing permissions from {module_id}: {e}")

        return total

    @classmethod
    @transaction.atomic
    def apply_module_role_defaults(cls, hub_id: str, module_id: str, role_permissions: dict) -> int:
        """
        Apply ROLE_PERMISSIONS defaults from a module's module.py.

        This creates RolePermission entries for each role/permission pair defined.
        Only applies if the role exists and permission entry doesn't already exist.

        Args:
            hub_id: Hub UUID
            module_id: Module identifier (e.g., 'inventory')
            role_permissions: Dict mapping role names to permission suffix lists
                Example: {"admin": ["*"], "manager": ["view_product", "add_product"]}

        Returns:
            Number of role permissions created
        """
        from apps.accounts.models import Role, Permission, RolePermission

        count = 0

        for role_name, perm_suffixes in role_permissions.items():
            # Get the role (skip if doesn't exist)
            try:
                role = Role.objects.get(
                    hub_id=hub_id,
                    name=role_name,
                    is_deleted=False
                )
            except Role.DoesNotExist:
                logger.debug(f"Role {role_name} not found, skipping module defaults")
                continue

            for suffix in perm_suffixes:
                if suffix == "*":
                    # Wildcard for all module permissions
                    wildcard = f"{module_id}.*"
                    rp, created = RolePermission.objects.get_or_create(
                        hub_id=hub_id,
                        role=role,
                        wildcard=wildcard,
                        defaults={'permission': None}
                    )
                    if created:
                        count += 1
                        logger.debug(f"Added wildcard {wildcard} to role {role_name}")
                else:
                    # Specific permission
                    codename = f"{module_id}.{suffix}"
                    try:
                        perm = Permission.objects.get(
                            hub_id=hub_id,
                            codename=codename,
                            is_deleted=False
                        )
                        rp, created = RolePermission.objects.get_or_create(
                            hub_id=hub_id,
                            role=role,
                            permission=perm,
                            defaults={'wildcard': ''}
                        )
                        if created:
                            count += 1
                            logger.debug(f"Added permission {codename} to role {role_name}")
                    except Permission.DoesNotExist:
                        logger.warning(f"Permission {codename} not found")

        if count > 0:
            logger.info(f"Applied {count} role permission defaults for {module_id}")

        return count

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
                    'source': 'basic',
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
    @transaction.atomic
    def create_solution_roles(cls, hub_id: str, roles_data: list) -> List:
        """
        Create/activate roles from a solution's role definitions.

        Called when user selects a solution during setup. Creates the
        solution-specific roles (e.g., cashier, waiter, kitchen) with
        their permission wildcards.

        Args:
            hub_id: Hub UUID
            roles_data: List of dicts from Cloud API with keys:
                role_name, role_display_name, role_description, wildcards

        Returns:
            List of created/updated Role instances
        """
        from apps.accounts.models import Role, RolePermission

        created_roles = []
        for role_data in roles_data:
            role, created = Role.objects.update_or_create(
                hub_id=hub_id,
                name=role_data['role_name'],
                defaults={
                    'display_name': role_data['role_display_name'],
                    'description': role_data.get('role_description', ''),
                    'is_system': True,
                    'is_active': True,
                    'source': 'solution',
                }
            )

            if created:
                logger.info(f"Created solution role: {role.name}")

            # Add wildcard permissions
            for wildcard in role_data.get('wildcards', []):
                RolePermission.objects.get_or_create(
                    hub_id=hub_id,
                    role=role,
                    wildcard=wildcard,
                    defaults={'permission': None}
                )

            created_roles.append(role)

        return created_roles

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

    @classmethod
    def get_role_permissions_for_module(cls, hub_id: str, role_id: str, module_id: str) -> dict:
        """
        Get the permissions a role has for a specific module.

        Args:
            hub_id: Hub UUID
            role_id: Role UUID
            module_id: Module identifier (e.g., 'inventory')

        Returns:
            Dict with:
            - permissions: List of permission dicts for the module
            - active_codenames: Set of codenames the role has
            - has_wildcard: True if role has module.* wildcard
        """
        from apps.accounts.models import Role, Permission, RolePermission

        role = Role.objects.get(id=role_id, hub_id=hub_id, is_deleted=False)

        # Get all permissions for the module
        permissions = list(
            Permission.objects.filter(
                hub_id=hub_id,
                module_id=module_id,
                is_deleted=False
            ).order_by('codename').values('id', 'codename', 'name', 'description')
        )

        # Check for module wildcard
        wildcard = f"{module_id}.*"
        has_wildcard = RolePermission.objects.filter(
            hub_id=hub_id,
            role=role,
            wildcard=wildcard,
            is_deleted=False
        ).exists()

        # Get expanded permissions for this role
        all_role_perms = role.get_all_permissions()

        # Filter to only this module's permissions
        active_codenames = {
            p['codename'] for p in permissions
            if p['codename'] in all_role_perms
        }

        return {
            'permissions': permissions,
            'active_codenames': active_codenames,
            'has_wildcard': has_wildcard,
            'active_count': len(active_codenames),
            'total_count': len(permissions),
        }

    @classmethod
    @transaction.atomic
    def toggle_role_permission(cls, hub_id: str, role_id: str, codename: str) -> bool:
        """
        Toggle a permission for a role.

        If the role has the permission, remove it. Otherwise, add it.

        Args:
            hub_id: Hub UUID
            role_id: Role UUID
            codename: Full permission codename (e.g., 'inventory.view_product')

        Returns:
            True if permission was added, False if removed
        """
        from apps.accounts.models import Role, Permission, RolePermission

        role = Role.objects.get(id=role_id, hub_id=hub_id, is_deleted=False)
        perm = Permission.objects.get(hub_id=hub_id, codename=codename, is_deleted=False)

        # Check if permission exists
        existing = RolePermission.objects.filter(
            hub_id=hub_id,
            role=role,
            permission=perm,
            is_deleted=False
        ).first()

        if existing:
            # Remove permission
            existing.is_deleted = True
            existing.save()
            logger.debug(f"Removed permission {codename} from role {role.name}")
            return False
        else:
            # Add permission
            RolePermission.objects.create(
                hub_id=hub_id,
                role=role,
                permission=perm,
                wildcard='',
            )
            logger.debug(f"Added permission {codename} to role {role.name}")
            return True

    @classmethod
    @transaction.atomic
    def toggle_role_module_wildcard(cls, hub_id: str, role_id: str, module_id: str) -> bool:
        """
        Toggle the module.* wildcard for a role.

        Args:
            hub_id: Hub UUID
            role_id: Role UUID
            module_id: Module identifier

        Returns:
            True if wildcard was added, False if removed
        """
        from apps.accounts.models import Role, RolePermission

        role = Role.objects.get(id=role_id, hub_id=hub_id, is_deleted=False)
        wildcard = f"{module_id}.*"

        # Check if wildcard exists
        existing = RolePermission.objects.filter(
            hub_id=hub_id,
            role=role,
            wildcard=wildcard,
            is_deleted=False
        ).first()

        if existing:
            # Remove wildcard
            existing.is_deleted = True
            existing.save()
            logger.debug(f"Removed wildcard {wildcard} from role {role.name}")
            return False
        else:
            # Add wildcard
            RolePermission.objects.create(
                hub_id=hub_id,
                role=role,
                permission=None,
                wildcard=wildcard,
            )
            logger.debug(f"Added wildcard {wildcard} to role {role.name}")
            return True

    @classmethod
    def get_modules_with_permissions(cls, hub_id: str) -> List[dict]:
        """
        Get all modules with their permissions for the role editor UI.

        Returns a list of modules with their permissions, sorted alphabetically.

        Args:
            hub_id: Hub UUID

        Returns:
            List of dicts with module info and permissions
        """
        from apps.accounts.models import Permission
        from apps.modules_runtime.loader import module_loader
        from importlib import import_module
        from collections import defaultdict

        # Get module metadata from dynamically loaded modules
        module_metadata = {}
        for module_id in module_loader.loaded_modules.keys():
            try:
                mod = import_module(f"{module_id}.module")
                module_metadata[module_id] = {
                    'name': str(getattr(mod, 'MODULE_NAME', module_id.title())),
                    'icon': getattr(mod, 'MODULE_ICON', 'cube-outline'),
                }
            except ImportError:
                module_metadata[module_id] = {
                    'name': module_id.title(),
                    'icon': 'cube-outline',
                }

        # Get permissions grouped by module
        permissions_by_module = defaultdict(list)
        for perm in Permission.objects.filter(hub_id=hub_id, is_deleted=False).order_by('codename'):
            permissions_by_module[perm.module_id].append({
                'id': str(perm.id),
                'codename': perm.codename,
                'name': str(perm.name),
                'description': perm.description or '',
            })

        # Build result list
        modules = []
        for module_id, perms in sorted(permissions_by_module.items()):
            meta = module_metadata.get(module_id, {'name': module_id.title(), 'icon': 'cube-outline'})
            modules.append({
                'id': module_id,
                'name': meta['name'],
                'icon': meta['icon'],
                'wildcard': f"{module_id}.*",
                'permissions': perms,
            })

        return modules
