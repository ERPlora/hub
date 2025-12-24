from django.db import models
from django.conf import settings
from django.core.cache import cache
from typing import Any, Optional


class SingletonConfigMixin:
    """
    Mixin para modelos de configuración singleton con caché.

    Proporciona:
    - Patrón Singleton (solo una instancia en DB)
    - Caché automático de la instancia completa
    - Acceso conveniente a campos individuales via get_value()
    - Invalidación automática de caché al guardar
    """

    CACHE_KEY_PREFIX = 'config'
    CACHE_TIMEOUT = 3600  # 1 hora

    def save(self, *args, **kwargs):
        """Override save para asegurar singleton e invalidar caché"""
        # Asegura que solo exista un registro con id=1
        if not self.pk:
            self.pk = 1

        # Si ya existe otra instancia, actualizamos la existente
        if self.pk != 1 and self.__class__.objects.filter(pk=1).exists():
            self.pk = 1

        super().save(*args, **kwargs)

        # Invalida el caché después de guardar
        self._clear_cache()

    def delete(self, *args, **kwargs):
        """Prevenir eliminación accidental del singleton"""
        # Solo permitir eliminación explícita
        if not kwargs.pop('force_delete', False):
            raise models.ProtectedError(
                "Cannot delete singleton configuration. Use force_delete=True if you really need to.",
                [self]
            )
        self._clear_cache()
        super().delete(*args, **kwargs)

    @classmethod
    def _get_cache_key(cls):
        """Genera la clave de caché para esta configuración"""
        return f'{cls.CACHE_KEY_PREFIX}_{cls.__name__.lower()}_instance'

    @classmethod
    def _clear_cache(cls):
        """Invalida el caché de esta configuración"""
        cache.delete(cls._get_cache_key())

    @classmethod
    def get_solo(cls):
        """
        Obtiene la instancia singleton con caché.

        Returns:
            Instancia del modelo de configuración
        """
        cache_key = cls._get_cache_key()
        instance = cache.get(cache_key)

        if instance is None:
            instance, _ = cls.objects.get_or_create(pk=1)
            cache.set(cache_key, instance, cls.CACHE_TIMEOUT)

        return instance

    @classmethod
    def get_config(cls):
        """Alias para compatibilidad con código existente"""
        return cls.get_solo()

    @classmethod
    def get_value(cls, field_name: str, default: Any = None) -> Any:
        """
        Obtiene el valor de un campo específico de la configuración.

        Args:
            field_name: Nombre del campo a obtener
            default: Valor por defecto si el campo no existe o es None

        Returns:
            Valor del campo o default

        Example:
            >>> currency = HubConfig.get_value('currency', 'USD')
            >>> is_configured = HubConfig.get_value('is_configured', False)
        """
        try:
            instance = cls.get_solo()
            value = getattr(instance, field_name, default)
            return value if value is not None else default
        except Exception:
            return default

    @classmethod
    def set_value(cls, field_name: str, value: Any) -> bool:
        """
        Establece el valor de un campo específico y guarda.

        Args:
            field_name: Nombre del campo a actualizar
            value: Nuevo valor

        Returns:
            True si se guardó correctamente, False en caso de error

        Example:
            >>> HubConfig.set_value('currency', 'EUR')
            >>> HubConfig.set_value('dark_mode', True)
        """
        try:
            instance = cls.get_solo()
            setattr(instance, field_name, value)
            instance.save()
            return True
        except Exception:
            return False

    @classmethod
    def update_values(cls, **kwargs) -> bool:
        """
        Actualiza múltiples campos a la vez.

        Args:
            **kwargs: Pares campo=valor a actualizar

        Returns:
            True si se guardó correctamente, False en caso de error

        Example:
            >>> HubConfig.update_values(
            ...     currency='EUR',
            ...     dark_mode=True,
            ...     auto_print=False
            ... )
        """
        try:
            instance = cls.get_solo()
            for field_name, value in kwargs.items():
                if hasattr(instance, field_name):
                    setattr(instance, field_name, value)
            instance.save()
            return True
        except Exception:
            return False

    @classmethod
    def get_all_values(cls) -> dict:
        """
        Obtiene todos los valores de configuración como diccionario.

        Returns:
            Dict con todos los campos y sus valores

        Example:
            >>> config = HubConfig.get_all_values()
            >>> print(config['currency'])  # 'USD'
            >>> print(config['dark_mode'])  # False
        """
        instance = cls.get_solo()
        return {
            field.name: getattr(instance, field.name)
            for field in instance._meta.fields
            if not field.name in ['id', 'created_at', 'updated_at']
        }


class HubConfig(SingletonConfigMixin, models.Model):
    """
    Hub configuration stored locally in SQLite.
    Contains hub credentials and configuration from Cloud.
    """
    # Cloud connection credentials
    hub_id = models.UUIDField(unique=True, null=True, blank=True)
    cloud_api_token = models.CharField(
        max_length=255,
        blank=True,
        help_text='Legacy token (deprecated, use hub_jwt instead)'
    )

    # JWT Authentication (Arquitectura Unificada Opción A)
    hub_jwt = models.TextField(
        blank=True,
        help_text='JWT token for Hub-to-Cloud authentication (RS256, 1 year)'
    )
    cloud_public_key = models.TextField(
        blank=True,
        help_text='Cloud RSA public key for validating command JWTs'
    )

    # Configuration flags
    is_configured = models.BooleanField(default=False)

    # Language configuration (detected from OS on first run)
    os_language = models.CharField(max_length=10, default='en')  # Detected from OS

    # Currency configuration
    currency = models.CharField(
        max_length=3,
        choices=settings.CURRENCY_CHOICES,
        default='EUR',
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
    dark_mode_auto = models.BooleanField(
        default=True,
        help_text='Use browser/OS preference for dark mode (ignores dark_mode field)'
    )
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


class TaxClass(models.Model):
    """
    Tax class configurable by the user.
    Users create their own tax types according to their country/region.

    Examples:
    - Spain: General 21%, Reduced 10%, Super-reduced 4%, Exempt 0%
    - Germany: Standard 19%, Reduced 7%
    - France: Normal 20%, Intermediate 10%, Reduced 5.5%
    - UK: Standard 20%, Reduced 5%, Zero 0%
    """
    name = models.CharField(
        max_length=100,
        verbose_name='Name',
        help_text='Display name for this tax class (e.g., "General 21%")'
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='Tax Rate (%)',
        help_text='Tax rate as percentage (e.g., 21.00 for 21%)'
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Description',
        help_text='Optional description or notes'
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name='Default',
        help_text='Use this tax class as default for new products'
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='Active',
        help_text='Inactive tax classes are hidden from selection'
    )
    order = models.IntegerField(
        default=0,
        verbose_name='Sort Order',
        help_text='Lower numbers appear first in lists'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tax Class'
        verbose_name_plural = 'Tax Classes'
        db_table = 'core_taxclass'
        ordering = ['order', 'rate']

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

    @classmethod
    def get_default(cls):
        """Get the default tax class, or None if not set."""
        return cls.objects.filter(is_default=True, is_active=True).first()

    @classmethod
    def get_active(cls):
        """Get all active tax classes ordered by sort order."""
        return cls.objects.filter(is_active=True).order_by('order', 'rate')

    def save(self, *args, **kwargs):
        # Ensure only one default tax class
        if self.is_default:
            TaxClass.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class StoreConfig(SingletonConfigMixin, models.Model):
    """
    Store configuration for receipts and business information.
    This is required for the POS to function properly.
    """
    # Business Information
    business_name = models.CharField(max_length=255, blank=True)

    # Default Tax Class (for products without category or category without tax_class)
    default_tax_class = models.ForeignKey(
        'TaxClass',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stores_as_default',
        verbose_name='Default Tax Class',
        help_text='Default tax class for products without category tax assignment'
    )
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

    def is_complete(self):
        """Check if minimum required fields are filled"""
        return bool(
            self.business_name and
            self.business_address and
            self.vat_number
        )


class BackupConfig(SingletonConfigMixin, models.Model):
    """
    Backup configuration for automated database backups.

    Supports both S3 (web/cloud) and local filesystem (desktop) storage,
    determined automatically by deployment mode.
    """

    class Frequency(models.TextChoices):
        DISABLED = 'disabled', 'Disabled'
        DAILY = 'daily', 'Daily'
        WEEKLY = 'weekly', 'Weekly'
        MONTHLY = 'monthly', 'Monthly'

    # Backup schedule
    enabled = models.BooleanField(
        default=False,
        help_text='Enable automatic backups'
    )
    frequency = models.CharField(
        max_length=20,
        choices=Frequency.choices,
        default=Frequency.DAILY,
        help_text='How often to run backups'
    )
    time_hour = models.PositiveSmallIntegerField(
        default=3,
        help_text='Hour to run backup (0-23, default 3 AM)'
    )
    time_minute = models.PositiveSmallIntegerField(
        default=0,
        help_text='Minute to run backup (0-59)'
    )

    # Retention
    retention_days = models.PositiveIntegerField(
        default=30,
        help_text='Days to keep backups (0 = keep forever)'
    )
    max_backups = models.PositiveIntegerField(
        default=10,
        help_text='Maximum number of backups to keep (0 = unlimited)'
    )

    # Last backup info
    last_backup_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Timestamp of last successful backup'
    )
    last_backup_size = models.PositiveIntegerField(
        default=0,
        help_text='Size of last backup in bytes'
    )
    last_backup_path = models.CharField(
        max_length=500,
        blank=True,
        help_text='Path/key of last backup'
    )
    last_error = models.TextField(
        blank=True,
        help_text='Last backup error message (empty if successful)'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Backup Configuration'
        verbose_name_plural = 'Backup Configuration'
        db_table = 'core_backupconfig'

    def __str__(self):
        if not self.enabled:
            return "Backup Config (Disabled)"
        return f"Backup Config ({self.frequency} at {self.time_hour:02d}:{self.time_minute:02d})"

    def get_cron_trigger_kwargs(self) -> dict:
        """
        Returns kwargs for APScheduler CronTrigger based on frequency.

        Returns:
            dict: Keyword arguments for CronTrigger
        """
        base = {
            'hour': self.time_hour,
            'minute': self.time_minute,
        }

        if self.frequency == self.Frequency.DAILY:
            return base  # Every day at specified time

        elif self.frequency == self.Frequency.WEEKLY:
            base['day_of_week'] = 'sun'  # Every Sunday
            return base

        elif self.frequency == self.Frequency.MONTHLY:
            base['day'] = 1  # First of each month
            return base

        return base  # Default to daily
