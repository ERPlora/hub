"""
Core models for ERPlora Hub.

This module provides base classes for all Hub models with:
- UUID primary keys (no conflicts when migrating to Cloud)
- hub_id for multi-tenancy (multiple Hubs sharing same PostgreSQL)
- Audit fields (created_by, updated_by, timestamps)
- Soft delete support
"""

from .base import HubBaseModel
from .managers import HubManager, HubManagerWithDeleted

__all__ = [
    'HubBaseModel',
    'HubManager',
    'HubManagerWithDeleted',
]
