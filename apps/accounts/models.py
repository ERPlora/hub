"""
Local user models for Hub authentication.

Models:
- Permission: Granular permissions from modules
- Role: Named collection of permissions
- RolePermission: Through model for Role-Permission M2M
- LocalUser: Hub users with role-based permissions
"""

from django.db import models
from django.contrib.auth.hashers import make_password, check_password

from apps.core.models import HubBaseModel, HubManager, HubManagerWithDeleted


# =============================================================================
# Permission Model
# =============================================================================

class Permission(HubBaseModel):
    """
    Granular permission for a specific action.

    Permissions are defined in each module's module.py PERMISSIONS list
    and synced to this table by PermissionService.

    Format: 'module.action_model'
    Examples:
        - 'inventory.view_product'
        - 'inventory.add_product'
        - 'sales.process_refund'
        - 'customers.export_data'

    Wildcards supported in Role assignment:
        - '*' = all permissions
        - 'inventory.*' = all inventory permissions
        - 'inventory.view_*' = all view permissions in inventory
    """

    codename = models.CharField(
        max_length=100,
        help_text="Permission codename (e.g., 'inventory.view_product')"
    )
    name = models.CharField(
        max_length=255,
        help_text="Human-readable name"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed description of what this permission allows"
    )
    module_id = models.CharField(
        max_length=50,
        help_text="Module that defines this permission"
    )

    objects = HubManager()
    all_objects = HubManagerWithDeleted()

    class Meta:
        verbose_name = 'Permission'
        verbose_name_plural = 'Permissions'
        ordering = ['module_id', 'codename']
        db_table = 'accounts_permissions'
        constraints = [
            models.UniqueConstraint(
                fields=['hub_id', 'codename'],
                condition=models.Q(is_deleted=False),
                name='unique_permission_codename_per_hub',
            ),
        ]
        indexes = [
            models.Index(fields=['hub_id', 'module_id']),
        ]

    def __str__(self):
        return f"{self.codename}: {self.name}"


# =============================================================================
# Role Model
# =============================================================================

class Role(HubBaseModel):
    """
    Named collection of permissions.

    Default roles created by PermissionService:
    - admin: Full access (all permissions via '*' wildcard)
    - manager: Management access (configurable)
    - employee: Basic access (configurable)

    Custom roles can be created by admin users.
    """

    name = models.CharField(
        max_length=50,
        help_text="Role name (e.g., 'admin', 'manager', 'cashier')"
    )
    display_name = models.CharField(
        max_length=100,
        help_text="Human-readable name for UI"
    )
    description = models.TextField(
        blank=True,
        help_text="Role description"
    )
    is_system = models.BooleanField(
        default=False,
        help_text="System roles cannot be deleted (admin, manager, employee)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive roles cannot be assigned to users"
    )

    # Permissions via through model (supports wildcards)
    permissions = models.ManyToManyField(
        Permission,
        through='RolePermission',
        related_name='roles',
        blank=True,
    )

    objects = HubManager()
    all_objects = HubManagerWithDeleted()

    class Meta:
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        ordering = ['name']
        db_table = 'accounts_roles'
        constraints = [
            models.UniqueConstraint(
                fields=['hub_id', 'name'],
                condition=models.Q(is_deleted=False),
                name='unique_role_name_per_hub',
            ),
        ]

    def __str__(self):
        return self.display_name or self.name

    def get_all_permissions(self):
        """
        Get all permission codenames for this role.

        Expands wildcards:
        - '*' -> all permissions
        - 'module.*' -> all permissions for module
        - 'module.action_*' -> all matching permissions
        """
        from apps.core.services.permission_service import PermissionService
        return PermissionService.expand_role_permissions(self)

    def has_perm(self, perm_codename):
        """Check if role has a specific permission (supports wildcards)."""
        return perm_codename in self.get_all_permissions()


# =============================================================================
# RolePermission Through Model
# =============================================================================

class RolePermission(HubBaseModel):
    """
    Through model for Role-Permission M2M relationship.

    Supports wildcard patterns in addition to direct permission links:
    - permission FK set = direct permission
    - permission FK null + wildcard set = pattern matching

    Wildcard examples:
    - '*' = all permissions
    - 'inventory.*' = all inventory module permissions
    - 'inventory.view_*' = all view permissions in inventory
    """

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='role_permissions',
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name='permission_roles',
        null=True,
        blank=True,
        help_text="Direct permission link (null if using wildcard)"
    )
    wildcard = models.CharField(
        max_length=100,
        blank=True,
        help_text="Wildcard pattern (e.g., '*', 'inventory.*')"
    )

    objects = HubManager()
    all_objects = HubManagerWithDeleted()

    class Meta:
        verbose_name = 'Role Permission'
        verbose_name_plural = 'Role Permissions'
        db_table = 'accounts_role_permissions'
        constraints = [
            models.UniqueConstraint(
                fields=['hub_id', 'role', 'permission'],
                condition=models.Q(is_deleted=False, permission__isnull=False),
                name='unique_role_permission',
            ),
            models.UniqueConstraint(
                fields=['hub_id', 'role', 'wildcard'],
                condition=models.Q(is_deleted=False, wildcard__gt=''),
                name='unique_role_wildcard',
            ),
        ]

    def __str__(self):
        if self.permission:
            return f"{self.role.name} -> {self.permission.codename}"
        return f"{self.role.name} -> {self.wildcard}"

    def clean(self):
        """Ensure either permission or wildcard is set, not both."""
        from django.core.exceptions import ValidationError
        if self.permission and self.wildcard:
            raise ValidationError("Set either permission or wildcard, not both.")
        if not self.permission and not self.wildcard:
            raise ValidationError("Must set either permission or wildcard.")


# =============================================================================
# LocalUser Model
# =============================================================================

class LocalUser(HubBaseModel):
    """
    Users stored in Hub's local database.

    Inherits from HubBaseModel:
    - id (UUID primary key)
    - hub_id (for multi-tenancy)
    - created_at, updated_at
    - created_by, updated_by
    - is_deleted, deleted_at (soft delete)

    There are TWO types of LocalUsers:

    1. CLOUD USERS (cloud_user_id is set):
       - Linked to Cloud account
       - Authenticate via Cloud SSO (email + password)
       - Created automatically when user logs in via Cloud
       - Can also use PIN for quick access

    2. LOCAL EMPLOYEES (cloud_user_id is NULL):
       - Created locally in Hub
       - Authenticate ONLY with 4-digit PIN
       - NOT synced to Cloud
       - Use cases: cashiers, employees without Cloud accounts

    The owner/admin who sets up the Hub is always a Cloud User.
    Additional employees can be either Cloud Users (invited) or Local Employees.
    """

    # Role choices (aligned with Cloud HubAccess model for consistency)
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('employee', 'Employee'),
    ]

    # Link to Cloud user (NULL = local-only employee with PIN auth)
    cloud_user_id = models.IntegerField(
        null=True,
        blank=True,
        help_text='Cloud user ID. NULL = local-only employee (PIN auth only)',
    )

    # User information
    email = models.EmailField(help_text='User email (unique per Hub)')
    name = models.CharField(max_length=255)

    # Local PIN authentication (4 digits)
    pin_hash = models.CharField(max_length=255)

    # User role and permissions
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    role_obj = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text="Role object for granular permissions. If null, uses legacy 'role' field."
    )
    extra_permissions = models.ManyToManyField(
        Permission,
        related_name='users_extra',
        blank=True,
        help_text="Additional permissions beyond role (for special cases)"
    )
    is_active = models.BooleanField(default=True)

    # User preferences
    language = models.CharField(max_length=10, default='en')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    # Authentication
    last_login = models.DateTimeField(null=True, blank=True)

    # Managers (override from HubBaseModel to ensure proper filtering)
    objects = HubManager()
    all_objects = HubManagerWithDeleted()

    class Meta:
        verbose_name = 'Local User'
        verbose_name_plural = 'Local Users'
        ordering = ['name']
        db_table = 'accounts_local_users'
        # Unique constraints per Hub (same email can exist in different Hubs)
        constraints = [
            models.UniqueConstraint(
                fields=['hub_id', 'email'],
                condition=models.Q(is_deleted=False),
                name='unique_email_per_hub',
            ),
            models.UniqueConstraint(
                fields=['hub_id', 'cloud_user_id'],
                condition=models.Q(is_deleted=False, cloud_user_id__isnull=False),
                name='unique_cloud_user_per_hub',
            ),
        ]
        indexes = [
            models.Index(fields=['hub_id', 'is_active']),
            models.Index(fields=['hub_id', 'role']),
        ]

    def __str__(self):
        return f"{self.name} ({self.email})"

    def set_pin(self, pin):
        """Hash and save PIN."""
        self.pin_hash = make_password(pin)
        self.save(update_fields=['pin_hash', 'updated_at'])

    def check_pin(self, pin):
        """Verify PIN."""
        return check_password(pin, self.pin_hash)

    def get_initials(self):
        """Return user initials for avatar."""
        words = self.name.split()
        if len(words) >= 2:
            return f"{words[0][0]}{words[1][0]}".upper()
        return self.name[0].upper() if self.name else "?"

    def get_role_color(self):
        """Return Ionic color for user role."""
        role_colors = {
            'admin': 'primary',
            'manager': 'tertiary',
            'employee': 'success',
        }
        return role_colors.get(self.get_role_name(), 'medium')

    def get_role_display(self):
        """Return human-readable role name for display."""
        if self.role_obj:
            return self.role_obj.display_name
        # Fallback to legacy role with capitalization
        return self.role.capitalize() if self.role else 'Employee'

    @property
    def is_cloud_user(self):
        """True if user is linked to Cloud account (can use SSO)."""
        return self.cloud_user_id is not None

    @property
    def is_local_only(self):
        """True if user is local-only (PIN auth only, not synced to Cloud)."""
        return self.cloud_user_id is None

    # Django-compatible authentication properties
    @property
    def is_authenticated(self):
        """Always return True for LocalUser instances (they are authenticated)."""
        return True

    @property
    def is_anonymous(self):
        """Always return False for LocalUser instances (they are not anonymous)."""
        return False

    @property
    def first_name(self):
        """Return first name from full name."""
        return self.name.split()[0] if self.name else ''

    @property
    def last_name(self):
        """Return last name from full name."""
        parts = self.name.split()
        return ' '.join(parts[1:]) if len(parts) > 1 else ''

    @property
    def username(self):
        """Return email as username for compatibility."""
        return self.email

    def get_username(self):
        """Return email as username for compatibility."""
        return self.email

    def get_full_name(self):
        """Return full name or empty string if not set."""
        return self.name if self.name else ''

    # =========================================================================
    # Permission Methods
    # =========================================================================

    def get_role_name(self):
        """
        Get the effective role name.

        Returns role_obj.name if set, otherwise falls back to legacy role field.
        """
        if self.role_obj:
            return self.role_obj.name
        return self.role

    def get_permissions(self):
        """
        Get all permission codenames for this user.

        Combines:
        1. Permissions from role_obj (with wildcard expansion)
        2. Extra permissions assigned directly to user

        Returns:
            set: Set of permission codenames
        """
        permissions = set()

        # Get permissions from role
        if self.role_obj:
            permissions.update(self.role_obj.get_all_permissions())

        # Add extra permissions
        for perm in self.extra_permissions.all():
            permissions.add(perm.codename)

        return permissions

    def has_perm(self, perm_codename):
        """
        Check if user has a specific permission.

        Admin users (role='admin' or role_obj.name='admin') have all permissions.

        Args:
            perm_codename: Permission codename (e.g., 'inventory.view_product')

        Returns:
            bool: True if user has permission
        """
        # Admin has all permissions
        if self.get_role_name() == 'admin':
            return True

        return perm_codename in self.get_permissions()

    def has_perms(self, perm_list):
        """
        Check if user has all permissions in list.

        Args:
            perm_list: List of permission codenames

        Returns:
            bool: True if user has ALL permissions
        """
        return all(self.has_perm(p) for p in perm_list)

    def has_any_perm(self, perm_list):
        """
        Check if user has any permission in list.

        Args:
            perm_list: List of permission codenames

        Returns:
            bool: True if user has ANY permission
        """
        return any(self.has_perm(p) for p in perm_list)

    def has_module_perms(self, module_id):
        """
        Check if user has any permission for a module.

        Args:
            module_id: Module identifier (e.g., 'inventory')

        Returns:
            bool: True if user has any permission for the module
        """
        if self.get_role_name() == 'admin':
            return True

        prefix = f"{module_id}."
        return any(p.startswith(prefix) for p in self.get_permissions())
