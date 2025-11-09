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


class SyncQueue(models.Model):
    """
    Queue de sincronización para operaciones offline.

    Almacena operaciones que deben sincronizarse con Cloud cuando
    el Hub recupere conexión a internet.
    """

    OPERATION_TYPES = [
        ('user_register', 'Register User'),
        ('user_remove', 'Remove User'),
        ('user_update', 'Update User'),
        ('plugin_install', 'Plugin Install'),
        ('plugin_uninstall', 'Plugin Uninstall'),
        ('sale_sync', 'Sale Sync'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    # Operation details
    operation_type = models.CharField(max_length=50, choices=OPERATION_TYPES)
    endpoint = models.CharField(max_length=500)  # API endpoint to call
    method = models.CharField(max_length=10, default='POST')  # HTTP method (POST, DELETE, PUT, PATCH)
    payload = models.JSONField(default=dict)  # Request body
    headers = models.JSONField(default=dict)  # Additional headers

    # Sync status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=5)
    last_error = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Sync Queue Item'
        verbose_name_plural = 'Sync Queue'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'next_retry_at']),
            models.Index(fields=['operation_type', 'status']),
        ]

    def __str__(self):
        return f"{self.operation_type} - {self.status} ({self.created_at})"

    @classmethod
    def add_operation(cls, operation_type, endpoint, method='POST', payload=None, headers=None):
        """
        Agregar operación a la cola de sincronización.

        Args:
            operation_type: Tipo de operación (user_register, user_remove, etc.)
            endpoint: URL del endpoint (sin dominio, ej: /api/hubs/{id}/users/{email}/)
            method: Método HTTP (POST, DELETE, PUT, PATCH)
            payload: Datos a enviar en el body
            headers: Headers adicionales (el X-Hub-Token se agrega automáticamente)

        Returns:
            SyncQueue: Item creado en la cola
        """
        return cls.objects.create(
            operation_type=operation_type,
            endpoint=endpoint,
            method=method.upper(),
            payload=payload or {},
            headers=headers or {}
        )

    @classmethod
    def get_pending_operations(cls, limit=10):
        """
        Obtener operaciones pendientes para sincronizar.

        Returns:
            QuerySet: Operaciones pendientes ordenadas por fecha de creación
        """
        from django.utils import timezone
        now = timezone.now()

        return cls.objects.filter(
            status='pending',
            retry_count__lt=models.F('max_retries')
        ).filter(
            models.Q(next_retry_at__isnull=True) | models.Q(next_retry_at__lte=now)
        ).order_by('created_at')[:limit]

    def mark_completed(self):
        """Marcar operación como completada."""
        from django.utils import timezone
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def mark_failed(self, error_message):
        """
        Marcar operación como fallida e incrementar contador de reintentos.

        Args:
            error_message: Mensaje de error
        """
        from django.utils import timezone
        from datetime import timedelta

        self.retry_count += 1
        self.last_error = error_message

        if self.retry_count >= self.max_retries:
            self.status = 'failed'
        else:
            self.status = 'pending'
            # Exponential backoff: 1min, 2min, 4min, 8min, 16min
            delay_minutes = 2 ** self.retry_count
            self.next_retry_at = timezone.now() + timedelta(minutes=delay_minutes)

        self.save(update_fields=['status', 'retry_count', 'last_error', 'next_retry_at', 'updated_at'])
