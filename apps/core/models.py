from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class HubConfig(models.Model):
    """
    Hub configuration stored locally in SQLite.
    Contains hub credentials and configuration from Cloud.
    """
    # Cloud connection credentials
    hub_id = models.UUIDField(unique=True, null=True, blank=True)
    tunnel_port = models.IntegerField(null=True, blank=True)
    tunnel_token = models.CharField(max_length=255, blank=True)

    # Configuration flags
    is_configured = models.BooleanField(default=False)

    # Language configuration (detected from OS on first run)
    os_language = models.CharField(max_length=10, default='en')  # Detected from OS

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Hub Configuration'
        verbose_name_plural = 'Hub Configuration'

    def __str__(self):
        return f"Hub Config (Configured: {self.is_configured})"

    @classmethod
    def get_config(cls):
        """Get or create hub configuration (singleton pattern)"""
        config, _ = cls.objects.get_or_create(id=1)
        return config


class LocalUser(models.Model):
    """
    Local users stored in Hub's SQLite database.
    These users are linked to Cloud users but can log in offline with PIN.
    """
    # User information from Cloud
    cloud_user_id = models.IntegerField(unique=True)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255)

    # Local authentication
    pin_hash = models.CharField(max_length=255)

    # User role and permissions
    role = models.CharField(max_length=50, default='cashier')  # admin, cashier, seller
    is_active = models.BooleanField(default=True)

    # User preferences
    language = models.CharField(max_length=10, default='en')  # User's preferred language

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Local User'
        verbose_name_plural = 'Local Users'
        ordering = ['name']

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
            'cashier': 'success',
            'seller': 'warning',
        }
        return role_colors.get(self.role, 'medium')
