"""
Custom managers for Hub models with automatic multi-tenancy filtering.

These managers ensure that each Hub only sees its own data when
multiple Hubs share the same PostgreSQL database.
"""

from django.db import models


class HubManager(models.Manager):
    """
    Default manager that automatically filters by current hub_id.

    Features:
    - Excludes soft-deleted records
    - Filters by hub_id from HubConfig
    - Each Hub only sees its own data

    Usage:
        # Normal queries are automatically filtered
        users = LocalUser.objects.all()  # Only users from current Hub

        # Access deleted records
        users = LocalUser.objects.with_deleted()

        # Access all Hubs (for reports, requires special permissions)
        users = LocalUser.objects.all_hubs()
    """

    def get_queryset(self):
        """
        Return queryset filtered by hub_id and excluding soft-deleted records.
        """
        qs = super().get_queryset()

        # Exclude soft-deleted records
        qs = qs.filter(is_deleted=False)

        # Filter by current hub_id
        hub_id = self._get_hub_id()
        if hub_id:
            qs = qs.filter(hub_id=hub_id)

        return qs

    def with_deleted(self):
        """
        Return queryset including soft-deleted records (current Hub only).

        Usage:
            # Get all users including deleted ones
            users = LocalUser.objects.with_deleted()

            # Get specific deleted user
            user = LocalUser.objects.with_deleted().get(email='deleted@example.com')
        """
        qs = super().get_queryset()
        hub_id = self._get_hub_id()
        if hub_id:
            qs = qs.filter(hub_id=hub_id)
        return qs

    def all_hubs(self):
        """
        Return queryset for ALL Hubs (excluding soft-deleted).

        WARNING: This bypasses multi-tenancy isolation.
        Only use for consolidated reports with proper authorization.

        Usage:
            # Cloud portal consolidated report
            all_sales = Sale.objects.all_hubs().aggregate(total=Sum('amount'))
        """
        return super().get_queryset().filter(is_deleted=False)

    def all_hubs_with_deleted(self):
        """
        Return unfiltered queryset for ALL Hubs including soft-deleted.

        WARNING: This bypasses all isolation. Use with extreme caution.
        Only for system maintenance and data recovery.
        """
        return super().get_queryset()

    def _get_hub_id(self):
        """
        Get current hub_id from HubConfig singleton.

        Returns None if HubConfig is not available (during migrations/tests).
        """
        try:
            from hub.apps.configuration.models import HubConfig
            config = HubConfig.get_solo()
            return config.hub_id
        except Exception:
            return None


class HubManagerWithDeleted(models.Manager):
    """
    Manager that includes soft-deleted records but still filters by hub_id.

    Use this when you need to access deleted records for:
    - Audit trails
    - Data recovery
    - Historical reports

    Usage:
        class MyModel(HubBaseModel):
            objects = HubManager()           # Default, excludes deleted
            all_objects = HubManagerWithDeleted()  # Includes deleted

        # Access deleted records
        deleted = MyModel.all_objects.filter(is_deleted=True)
    """

    def get_queryset(self):
        """
        Return queryset filtered by hub_id but including soft-deleted records.
        """
        qs = super().get_queryset()

        # Filter by current hub_id
        hub_id = self._get_hub_id()
        if hub_id:
            qs = qs.filter(hub_id=hub_id)

        return qs

    def _get_hub_id(self):
        """
        Get current hub_id from HubConfig singleton.
        """
        try:
            from hub.apps.configuration.models import HubConfig
            config = HubConfig.get_solo()
            return config.hub_id
        except Exception:
            return None
