from django.db import models
from django.conf import settings


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

    # Currency configuration
    currency = models.CharField(
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
        default='USD',
        help_text='Currency used for transactions in this Hub'
    )

    @property
    def CURRENCY_CHOICES(self):
        """Compatibility property for existing code"""
        return settings.CURRENCY_CHOICES

    # Theme preferences
    color_theme = models.CharField(max_length=20, default='default', choices=[
        ('default', 'Default (Gray)'),
        ('blue', 'Blue'),
    ])
    dark_mode = models.BooleanField(default=False)
    auto_print = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Hub Configuration'
        verbose_name_plural = 'Hub Configuration'
        db_table = 'core_hubconfig'  # Keep existing table name

    def __str__(self):
        return f"Hub Config (Configured: {self.is_configured})"

    @classmethod
    def get_config(cls):
        """Get or create hub configuration (singleton pattern)"""
        config, _ = cls.objects.get_or_create(id=1)
        return config


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
        db_table = 'core_storeconfig'  # Keep existing table name

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
