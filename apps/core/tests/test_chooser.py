"""
Tests for ERPlora Generic Chooser System.

Tests the ChooserRegistry, ChooserConfig, and chooser functionality
that provides reusable model selection components.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from django.db import models
from django.db.models import Q

from apps.core.chooser import ChooserConfig, ChooserRegistry, chooser_registry


class TestChooserConfig:
    """Tests for ChooserConfig."""

    def _make_mock_model(self, app_label='test', model_name='item'):
        """Create a mock Django model class."""
        model = MagicMock()
        model._meta = MagicMock()
        model._meta.app_label = app_label
        model._meta.model_name = model_name
        model._meta.verbose_name_plural = 'items'
        model.__name__ = 'Item'
        return model

    def test_key_from_model(self):
        """Key is generated from app_label.model_name."""
        model = self._make_mock_model('inventory', 'product')
        config = ChooserConfig(model=model, search_fields=['name'])
        assert config.key == 'inventory.product'

    def test_default_label_from_model(self):
        """Label defaults to model's verbose_name_plural."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'])
        assert config.label == 'Items'

    def test_custom_label(self):
        """Custom label overrides default."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'], label='My Items')
        assert config.label == 'My Items'

    def test_default_values(self):
        """Default values are set correctly."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'])
        assert config.icon == 'search-outline'
        assert config.per_page == 20
        assert config.image_field is None
        assert config.subtitle_field is None
        assert config.filters == {}

    def test_search_builds_q_objects(self):
        """search() creates icontains Q for each search field."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name', 'sku'])

        qs = MagicMock()
        filtered_qs = MagicMock()
        qs.filter.return_value = filtered_qs

        result = config.search(qs, 'test')

        # Verify filter was called
        qs.filter.assert_called_once()
        assert result == filtered_qs

    def test_search_empty_query_noop(self):
        """search() with empty query returns queryset unchanged."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'])

        qs = MagicMock()
        result = config.search(qs, '')
        assert result == qs

    def test_search_none_query_noop(self):
        """search() with None query returns queryset unchanged."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'])

        qs = MagicMock()
        result = config.search(qs, None)
        assert result == qs

    def test_get_display_value_default(self):
        """get_display_value defaults to str()."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'])

        obj = MagicMock()
        obj.__str__ = MagicMock(return_value='Test Item')

        result = config.get_display_value(obj)
        assert result == str(obj)

    def test_get_display_value_custom(self):
        """Custom display_fn is used when provided."""
        model = self._make_mock_model()
        display_fn = lambda obj: f"Custom: {obj.name}"
        config = ChooserConfig(model=model, search_fields=['name'], display_fn=display_fn)

        obj = MagicMock()
        obj.name = 'Widget'

        result = config.get_display_value(obj)
        assert result == 'Custom: Widget'

    def test_get_subtitle(self):
        """get_subtitle returns subtitle_field value."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'], subtitle_field='sku')

        obj = MagicMock()
        obj.sku = 'SKU-001'

        result = config.get_subtitle(obj)
        assert result == 'SKU-001'

    def test_get_subtitle_no_field(self):
        """get_subtitle returns empty string when no subtitle_field."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'])

        obj = MagicMock()
        result = config.get_subtitle(obj)
        assert result == ''

    def test_apply_filters(self):
        """apply_filters adds filter conditions to queryset."""
        model = self._make_mock_model()
        config = ChooserConfig(
            model=model,
            search_fields=['name'],
            filters={'category': {'field': 'category_id', 'label': 'Category'}},
        )

        qs = MagicMock()
        qs.filter.return_value = qs

        result = config.apply_filters(qs, {'category': '123'})
        qs.filter.assert_called_once_with(category_id='123')

    def test_apply_filters_ignores_unknown(self):
        """apply_filters ignores filter keys not in config."""
        model = self._make_mock_model()
        config = ChooserConfig(model=model, search_fields=['name'])

        qs = MagicMock()
        result = config.apply_filters(qs, {'unknown': 'value'})
        qs.filter.assert_not_called()

    def test_apply_filters_ignores_empty_values(self):
        """apply_filters ignores empty filter values."""
        model = self._make_mock_model()
        config = ChooserConfig(
            model=model,
            search_fields=['name'],
            filters={'category': {'field': 'category_id', 'label': 'Category'}},
        )

        qs = MagicMock()
        result = config.apply_filters(qs, {'category': ''})
        qs.filter.assert_not_called()


class TestChooserRegistry:
    """Tests for ChooserRegistry."""

    def setup_method(self):
        self.registry = ChooserRegistry()

    def _make_mock_model(self, app_label='test', model_name='item'):
        model = MagicMock()
        model._meta = MagicMock()
        model._meta.app_label = app_label
        model._meta.model_name = model_name
        model._meta.verbose_name_plural = 'items'
        return model

    def test_register_and_get(self):
        """Register a model and retrieve its config."""
        model = self._make_mock_model('inventory', 'product')
        config = self.registry.register(model, {'search_fields': ['name']})

        assert self.registry.get('inventory.product') is config

    def test_get_nonexistent(self):
        """get() returns None for unregistered model."""
        assert self.registry.get('nonexistent.model') is None

    def test_register_returns_config(self):
        """register() returns the created ChooserConfig."""
        model = self._make_mock_model()
        result = self.registry.register(model, {'search_fields': ['name']})
        assert isinstance(result, ChooserConfig)

    def test_get_all(self):
        """get_all() returns all registered configs."""
        model1 = self._make_mock_model('app1', 'model1')
        model2 = self._make_mock_model('app2', 'model2')

        self.registry.register(model1, {'search_fields': ['name']})
        self.registry.register(model2, {'search_fields': ['name']})

        all_configs = self.registry.get_all()
        assert len(all_configs) == 2
        assert 'app1.model1' in all_configs
        assert 'app2.model2' in all_configs

    def test_unregister(self):
        """unregister() removes a model config."""
        model = self._make_mock_model()
        self.registry.register(model, {'search_fields': ['name']})

        result = self.registry.unregister('test.item')
        assert result is True
        assert self.registry.get('test.item') is None

    def test_unregister_nonexistent(self):
        """unregister() returns False for nonexistent key."""
        result = self.registry.unregister('nonexistent.model')
        assert result is False

    def test_clear_module(self):
        """clear_module() removes all configs from a module."""
        model1 = self._make_mock_model('mymod', 'model1')
        model2 = self._make_mock_model('mymod', 'model2')
        model3 = self._make_mock_model('other', 'model3')

        self.registry.register(model1, {'search_fields': ['name']})
        self.registry.register(model2, {'search_fields': ['name']})
        self.registry.register(model3, {'search_fields': ['name']})

        removed = self.registry.clear_module('mymod')
        assert removed == 2
        assert self.registry.get('mymod.model1') is None
        assert self.registry.get('mymod.model2') is None
        assert self.registry.get('other.model3') is not None

    def test_clear_all(self):
        """clear_all() empties the registry."""
        model = self._make_mock_model()
        self.registry.register(model, {'search_fields': ['name']})

        self.registry.clear_all()
        assert len(self.registry.get_all()) == 0

    def test_overwrite_registration(self):
        """Re-registering a model overwrites the previous config."""
        model = self._make_mock_model()

        self.registry.register(model, {'search_fields': ['name'], 'per_page': 10})
        self.registry.register(model, {'search_fields': ['name', 'sku'], 'per_page': 50})

        config = self.registry.get('test.item')
        assert config.search_fields == ['name', 'sku']
        assert config.per_page == 50


class TestGlobalRegistry:
    """Tests for the global chooser_registry instance."""

    def test_global_instance_exists(self):
        """Global chooser_registry is a ChooserRegistry."""
        assert isinstance(chooser_registry, ChooserRegistry)
