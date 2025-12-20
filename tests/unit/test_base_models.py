"""
Unit tests for base models.

Tests TimeStampedModel, ActiveModel, and HubBaseModel.
"""
import pytest
from datetime import datetime
from django.db import models
from django.utils import timezone

pytestmark = pytest.mark.unit


class TestTimeStampedModel:
    """Tests for TimeStampedModel abstract base."""

    def test_model_has_timestamps(self, db):
        """Test that TimeStampedModel provides timestamp fields."""
        from apps.core.models import TimeStampedModel

        # Check the abstract model has the fields
        fields = {f.name for f in TimeStampedModel._meta.get_fields()}

        assert 'created_at' in fields
        assert 'updated_at' in fields

    def test_timestamps_are_auto(self):
        """Test that timestamps are auto-set."""
        from apps.core.models import TimeStampedModel

        for field in TimeStampedModel._meta.get_fields():
            if field.name == 'created_at':
                assert field.auto_now_add is True
            elif field.name == 'updated_at':
                assert field.auto_now is True


class TestActiveModel:
    """Tests for ActiveModel abstract base."""

    def test_model_has_is_active(self, db):
        """Test that ActiveModel provides is_active field."""
        from apps.core.models import ActiveModel

        fields = {f.name for f in ActiveModel._meta.get_fields()}

        assert 'is_active' in fields
        assert 'created_at' in fields  # Inherited from TimeStampedModel
        assert 'updated_at' in fields

    def test_is_active_default_true(self):
        """Test that is_active defaults to True."""
        from apps.core.models import ActiveModel

        for field in ActiveModel._meta.get_fields():
            if field.name == 'is_active':
                assert field.default is True


class TestHubBaseModel:
    """Tests for HubBaseModel."""

    def test_model_has_uuid_pk(self):
        """Test that HubBaseModel uses UUID as primary key."""
        from apps.core.models import HubBaseModel

        pk_field = HubBaseModel._meta.pk

        assert pk_field.name == 'id'
        assert isinstance(pk_field, models.UUIDField)

    def test_model_has_hub_id(self):
        """Test that HubBaseModel has hub_id field."""
        from apps.core.models import HubBaseModel

        fields = {f.name for f in HubBaseModel._meta.get_fields()}

        assert 'hub_id' in fields

    def test_model_has_audit_fields(self):
        """Test that HubBaseModel has audit fields."""
        from apps.core.models import HubBaseModel

        fields = {f.name for f in HubBaseModel._meta.get_fields()}

        assert 'created_at' in fields
        assert 'updated_at' in fields
        assert 'created_by' in fields
        assert 'updated_by' in fields

    def test_model_has_soft_delete(self):
        """Test that HubBaseModel has soft delete fields."""
        from apps.core.models import HubBaseModel

        fields = {f.name for f in HubBaseModel._meta.get_fields()}

        assert 'is_deleted' in fields
        assert 'deleted_at' in fields

    def test_is_deleted_default_false(self):
        """Test that is_deleted defaults to False."""
        from apps.core.models import HubBaseModel

        for field in HubBaseModel._meta.get_fields():
            if field.name == 'is_deleted':
                assert field.default is False
