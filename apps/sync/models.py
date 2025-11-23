from django.db import models


class TokenCache(models.Model):
    """
    Cache for JWT tokens and RSA public key.

    Enables offline JWT validation by storing:
    - Last valid JWT access token
    - RSA public key from Cloud
    - Cache timestamps for expiration
    """
    # JWT token cache
    jwt_access_token = models.TextField(blank=True)
    jwt_refresh_token = models.TextField(blank=True)
    jwt_cached_at = models.DateTimeField(null=True, blank=True)

    # RSA public key cache
    rsa_public_key = models.TextField(blank=True)
    public_key_cached_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Token Cache'
        verbose_name_plural = 'Token Cache'
        db_table = 'core_tokencache'  # Keep existing table name

    def __str__(self):
        return f"Token Cache (Updated: {self.updated_at})"

    @classmethod
    def get_cache(cls):
        """Get or create token cache (singleton pattern)"""
        cache, _ = cls.objects.get_or_create(id=1)
        return cache

    def cache_jwt_tokens(self, access_token, refresh_token=None):
        """Cache JWT tokens"""
        from django.utils import timezone
        self.jwt_access_token = access_token
        if refresh_token:
            self.jwt_refresh_token = refresh_token
        self.jwt_cached_at = timezone.now()
        self.save()

    def cache_public_key(self, public_key):
        """Cache RSA public key"""
        from django.utils import timezone
        self.rsa_public_key = public_key
        self.public_key_cached_at = timezone.now()
        self.save()

    def get_cached_jwt(self):
        """Get cached JWT access token"""
        return self.jwt_access_token if self.jwt_access_token else None

    def get_cached_public_key(self):
        """Get cached RSA public key"""
        return self.rsa_public_key if self.rsa_public_key else None


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
        db_table = 'core_syncqueue'  # Keep existing table name
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
