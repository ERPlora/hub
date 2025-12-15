from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class LocalUser(models.Model):
    """
    Users stored in Hub's local SQLite database.

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
    # Role choices (aligned with Cloud HubUser model for consistency)
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('employee', 'Employee'),
    ]

    # Link to Cloud user (NULL = local-only employee with PIN auth)
    cloud_user_id = models.IntegerField(
        unique=True,
        null=True,
        blank=True,
        help_text='Cloud user ID. NULL = local-only employee (PIN auth only)'
    )

    # User information
    email = models.EmailField(unique=True, help_text='Unique identifier')
    name = models.CharField(max_length=255)

    # Local PIN authentication (4 digits)
    pin_hash = models.CharField(max_length=255)

    # User role and permissions
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='employee')
    is_active = models.BooleanField(default=True)

    # User preferences
    language = models.CharField(max_length=10, default='en')  # User's preferred language
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)  # User avatar

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Local User'
        verbose_name_plural = 'Local Users'
        ordering = ['name']
        db_table = 'core_localuser'  # Keep existing table name

    def __str__(self):
        return f"{self.name} ({self.email})"

    def set_pin(self, pin):
        """Hash and save PIN"""
        self.pin_hash = make_password(pin)
        self.save()

    def check_pin(self, pin):
        """Verify PIN"""
        return check_password(pin, self.pin_hash)

    def get_initials(self):
        """Return user initials for avatar"""
        words = self.name.split()
        if len(words) >= 2:
            return f"{words[0][0]}{words[1][0]}".upper()
        return self.name[0].upper() if self.name else "?"

    def get_role_color(self):
        """Return Ionic color for user role"""
        role_colors = {
            'admin': 'primary',
            'manager': 'tertiary',
            'employee': 'success',
        }
        return role_colors.get(self.role, 'medium')

    @property
    def is_cloud_user(self):
        """True if user is linked to Cloud account (can use SSO)"""
        return self.cloud_user_id is not None

    @property
    def is_local_only(self):
        """True if user is local-only (PIN auth only, not synced to Cloud)"""
        return self.cloud_user_id is None

    # Django-compatible authentication properties
    @property
    def is_authenticated(self):
        """Always return True for LocalUser instances (they are authenticated)"""
        return True

    @property
    def is_anonymous(self):
        """Always return False for LocalUser instances (they are not anonymous)"""
        return False

    @property
    def first_name(self):
        """Return first name from full name"""
        return self.name.split()[0] if self.name else ''

    @property
    def last_name(self):
        """Return last name from full name"""
        parts = self.name.split()
        return ' '.join(parts[1:]) if len(parts) > 1 else ''

    @property
    def username(self):
        """Return email as username for compatibility"""
        return self.email

    def get_username(self):
        """Return email as username for compatibility"""
        return self.email

    def get_full_name(self):
        """Return full name or empty string if not set"""
        return self.name if self.name else ''
