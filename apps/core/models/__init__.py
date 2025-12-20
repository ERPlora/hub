"""
Core models for ERPlora Hub.

This module provides base classes for all Hub and Plugin models:

Simple models (for plugins):
- TimeStampedModel: Just created_at/updated_at
- ActiveModel: TimeStamped + is_active flag

Full-featured models (for core Hub):
- HubBaseModel: UUID primary key, multi-tenancy, soft delete, audit fields

Usage in plugins:
    from apps.core.models import TimeStampedModel, ActiveModel

    class Product(TimeStampedModel):
        name = models.CharField(max_length=255)

    class Category(ActiveModel):
        name = models.CharField(max_length=255)
"""

from .base import TimeStampedModel, ActiveModel, HubBaseModel
from .managers import HubManager, HubManagerWithDeleted

__all__ = [
    # Simple base models for plugins
    'TimeStampedModel',
    'ActiveModel',
    # Full-featured base model for Hub core
    'HubBaseModel',
    # Managers
    'HubManager',
    'HubManagerWithDeleted',
]
