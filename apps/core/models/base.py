"""
Base models for all Hub and Plugin models.

Provides:
- TimeStampedModel: Simple base with created_at/updated_at
- HubBaseModel: Full features with UUID, multi-tenancy, soft delete
"""

import uuid
from django.db import models
from django.utils import timezone

from .managers import HubManager, HubManagerWithDeleted


class TimeStampedModel(models.Model):
    """
    Simple abstract base model with timestamps.

    Use this for plugins that don't need UUID primary keys or multi-tenancy.

    Features:
    - created_at: Auto-set on creation
    - updated_at: Auto-updated on save

    Usage in plugins:
        from apps.core.models import TimeStampedModel

        class Product(TimeStampedModel):
            name = models.CharField(max_length=255)
            price = models.DecimalField(max_digits=10, decimal_places=2)

            class Meta(TimeStampedModel.Meta):
                db_table = 'inventory_product'
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActiveModel(TimeStampedModel):
    """
    Abstract base model with is_active flag.

    Use for models that need activation/deactivation without deletion.

    Features:
    - is_active: Boolean flag for soft activation
    - created_at, updated_at: From TimeStampedModel

    Usage in plugins:
        from apps.core.models import ActiveModel

        class Category(ActiveModel):
            name = models.CharField(max_length=255)

            class Meta(ActiveModel.Meta):
                db_table = 'inventory_category'

        # Query active only
        Category.objects.filter(is_active=True)
    """

    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        abstract = True


class HubBaseModel(models.Model):
    """
    Abstract base model for all Hub models.

    Features:
    - UUID as primary key (no ID conflicts when migrating Desktop Hub to Cloud)
    - hub_id for multi-tenancy (multiple Hubs sharing same PostgreSQL database)
    - Audit fields: created_by, updated_by, timestamps
    - Soft delete support with is_deleted flag

    Usage:
        class MyModel(HubBaseModel):
            name = models.CharField(max_length=255)

            class Meta(HubBaseModel.Meta):
                db_table = 'myapp_mymodel'

    The hub_id is automatically set from HubConfig when saving.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Multi-tenancy: each record belongs to a Hub
    # This enables multiple Hubs to share the same PostgreSQL database
    # while keeping their data isolated
    hub_id = models.UUIDField(
        db_index=True,
        editable=False,
        null=True,  # Allow null during migration, will be required after
        blank=True,
        help_text="Hub this record belongs to (for multi-tenancy)",
    )

    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.UUIDField(
        null=True,
        blank=True,
        help_text="UUID of the user who created this record",
    )

    updated_by = models.UUIDField(
        null=True,
        blank=True,
        help_text="UUID of the user who last updated this record",
    )

    # Soft delete
    is_deleted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Soft delete flag - record is hidden but not removed",
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when record was soft deleted",
    )

    # Managers
    objects = HubManager()
    all_objects = HubManagerWithDeleted()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        Override save to auto-assign hub_id from HubConfig.

        The hub_id is set automatically on first save if not provided.
        This ensures all records are properly associated with a Hub.
        """
        if not self.hub_id:
            try:
                from apps.configuration.models import HubConfig
                config = HubConfig.get_solo()
                if config.hub_id:
                    self.hub_id = config.hub_id
            except Exception:
                # During migrations or tests, HubConfig may not be available
                pass

        super().save(*args, **kwargs)

    def delete(self, *args, hard_delete: bool = False, **kwargs):
        """
        Soft delete by default, hard delete if explicitly requested.

        Args:
            hard_delete: If True, permanently delete the record.
                        If False (default), mark as deleted but keep in DB.

        Usage:
            obj.delete()              # Soft delete
            obj.delete(hard_delete=True)  # Permanent delete
        """
        if hard_delete:
            super().delete(*args, **kwargs)
        else:
            self.is_deleted = True
            self.deleted_at = timezone.now()
            self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def restore(self):
        """
        Restore a soft-deleted record.

        Usage:
            obj = MyModel.all_objects.get(pk=uuid)
            obj.restore()
        """
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def hard_delete(self):
        """
        Convenience method for permanent deletion.

        Usage:
            obj.hard_delete()  # Same as obj.delete(hard_delete=True)
        """
        self.delete(hard_delete=True)
