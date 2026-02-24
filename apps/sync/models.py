"""
Synchronization models for Hub-Cloud communication.
"""

from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import HubBaseModel, HubManager, HubManagerWithDeleted


class TokenCache(models.Model):
    """
    Cache for JWT tokens and RSA public key.

    This is a singleton model (pk=1) that stores authentication tokens
    for Hub-to-Cloud communication.

    Note: This does NOT inherit from HubBaseModel because:
    - It's a singleton per Hub instance
    - It stores Hub-wide configuration, not per-record data
    - The hub_id is in HubConfig, not needed here
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
        verbose_name = _('Token Cache')
        verbose_name_plural = _('Token Cache')
        db_table = 'sync_tokencache'

    def __str__(self):
        return f"Token Cache (Updated: {self.updated_at})"

    def save(self, *args, **kwargs):
        """Ensure singleton pattern (pk=1)."""
        if not self.pk:
            self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_cache(cls):
        """Get or create token cache (singleton pattern)."""
        cache, _ = cls.objects.get_or_create(pk=1)
        return cache

    def cache_jwt_tokens(self, access_token, refresh_token=None):
        """Cache JWT tokens."""
        self.jwt_access_token = access_token
        if refresh_token:
            self.jwt_refresh_token = refresh_token
        self.jwt_cached_at = timezone.now()
        self.save(update_fields=['jwt_access_token', 'jwt_refresh_token', 'jwt_cached_at', 'updated_at'])

    def cache_public_key(self, public_key):
        """Cache RSA public key."""
        self.rsa_public_key = public_key
        self.public_key_cached_at = timezone.now()
        self.save(update_fields=['rsa_public_key', 'public_key_cached_at', 'updated_at'])

    def get_cached_jwt(self):
        """Get cached JWT access token."""
        return self.jwt_access_token if self.jwt_access_token else None

    def get_cached_public_key(self):
        """Get cached RSA public key."""
        return self.rsa_public_key if self.rsa_public_key else None


class SyncQueue(HubBaseModel):
    """
    Queue for offline synchronization operations.

    Stores operations that must be synchronized with Cloud when
    the Hub regains internet connection.

    Inherits from HubBaseModel:
    - id (UUID primary key)
    - hub_id (for multi-tenancy)
    - created_at, updated_at
    - created_by, updated_by
    - is_deleted, deleted_at (soft delete)
    """

    OPERATION_TYPES = [
        ('user_register', 'Register User'),
        ('user_remove', 'Remove User'),
        ('user_update', 'Update User'),
        ('module_install', 'Module Install'),
        ('module_uninstall', 'Module Uninstall'),
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
    endpoint = models.CharField(max_length=500, help_text='API endpoint to call')
    method = models.CharField(max_length=10, default='POST', help_text='HTTP method')
    payload = models.JSONField(default=dict, help_text='Request body')
    headers = models.JSONField(default=dict, help_text='Additional headers')

    # Sync status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=5)
    last_error = models.TextField(blank=True)

    # Timing
    completed_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    # Managers
    objects = HubManager()
    all_objects = HubManagerWithDeleted()

    class Meta:
        verbose_name = _('Sync Queue Item')
        verbose_name_plural = _('Sync Queue')
        ordering = ['created_at']
        db_table = 'sync_syncqueue'
        indexes = [
            models.Index(fields=['hub_id', 'status', 'next_retry_at']),
            models.Index(fields=['hub_id', 'operation_type', 'status']),
        ]

    def __str__(self):
        return f"{self.operation_type} - {self.status} ({self.created_at})"

    @classmethod
    def add_operation(cls, operation_type, endpoint, method='POST', payload=None, headers=None):
        """
        Add operation to the sync queue.

        Args:
            operation_type: Type of operation (user_register, user_remove, etc.)
            endpoint: API endpoint URL (without domain)
            method: HTTP method (POST, DELETE, PUT, PATCH)
            payload: Data to send in request body
            headers: Additional headers (X-Hub-Token added automatically)

        Returns:
            SyncQueue: Created queue item
        """
        return cls.objects.create(
            operation_type=operation_type,
            endpoint=endpoint,
            method=method.upper(),
            payload=payload or {},
            headers=headers or {},
        )

    @classmethod
    def get_pending_operations(cls, limit=10):
        """
        Get pending operations for synchronization.

        Returns:
            QuerySet: Pending operations ordered by creation date
        """
        now = timezone.now()

        return cls.objects.filter(
            status='pending',
            retry_count__lt=models.F('max_retries'),
        ).filter(
            models.Q(next_retry_at__isnull=True) | models.Q(next_retry_at__lte=now)
        ).order_by('created_at')[:limit]

    def mark_completed(self):
        """Mark operation as completed."""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def mark_failed(self, error_message):
        """
        Mark operation as failed and increment retry counter.

        Args:
            error_message: Error message to store
        """
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
