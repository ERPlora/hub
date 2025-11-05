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


class StoreConfig(models.Model):
    """
    Store configuration for receipts and business information.
    This is required for the POS to function properly.
    """
    # Business Information
    business_name = models.CharField(max_length=255, blank=True)
    business_address = models.TextField(blank=True)
    vat_number = models.CharField(max_length=100, blank=True, verbose_name='VAT/Tax ID')
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    # Logo/Image
    logo = models.ImageField(upload_to='store/', blank=True, null=True)

    # Tax Configuration
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text='Tax rate in percentage (e.g., 21.00 for 21%)')
    tax_included = models.BooleanField(default=True, help_text='Tax included in prices')

    # Receipt Configuration
    receipt_header = models.TextField(blank=True, help_text='Additional text to show at the top of receipts')
    receipt_footer = models.TextField(blank=True, help_text='Additional text to show at the bottom of receipts')

    # Configuration status
    is_configured = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Store Configuration'
        verbose_name_plural = 'Store Configuration'

    def __str__(self):
        return f"{self.business_name or 'Store'} (Configured: {self.is_configured})"

    @classmethod
    def get_config(cls):
        """Get or create store configuration (singleton pattern)"""
        config, _ = cls.objects.get_or_create(id=1)
        return config

    def is_complete(self):
        """Check if minimum required fields are filled"""
        return bool(
            self.business_name and
            self.business_address and
            self.vat_number
        )


class Plugin(models.Model):
    """
    Installed plugins in the Hub.
    Plugins extend the functionality of the POS system.
    """
    # Plugin identification
    plugin_id = models.CharField(max_length=100, unique=True)  # e.g., 'cpos-pos', 'cpos-inventory'
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=50)

    # Plugin metadata
    author = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=50, default='extension-puzzle-outline')
    category = models.CharField(max_length=50, default='general')  # pos, inventory, reports, etc.

    # Installation status
    is_installed = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    install_path = models.CharField(max_length=500, blank=True)

    # Menu configuration
    menu_label = models.CharField(max_length=100, blank=True)
    menu_icon = models.CharField(max_length=50, blank=True)
    menu_order = models.IntegerField(default=100)
    show_in_menu = models.BooleanField(default=True)

    # URLs
    main_url = models.CharField(max_length=200, blank=True)  # Main entry point URL

    # Timestamps
    installed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plugin'
        verbose_name_plural = 'Plugins'
        ordering = ['menu_order', 'name']

    def __str__(self):
        return f"{self.name} v{self.version}"
