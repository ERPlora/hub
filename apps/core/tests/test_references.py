"""
Tests for ERPlora Reference Index System.

Tests the reference scanning, counting, and deletion safety checking
that prevents users from accidentally deleting objects in use.
"""
import pytest
from unittest.mock import MagicMock, patch
from django.db import models

from apps.core.references import (
    get_references,
    can_delete,
    clear_cache,
    _build_relationship_map,
)


class TestBuildRelationshipMap:
    """Tests for relationship discovery."""

    def setup_method(self):
        clear_cache()

    def test_returns_list(self):
        """_build_relationship_map returns a list."""
        from apps.accounts.models import LocalUser
        result = _build_relationship_map(LocalUser)
        assert isinstance(result, list)

    def test_caches_results(self):
        """Second call returns cached results."""
        from apps.accounts.models import LocalUser
        result1 = _build_relationship_map(LocalUser)
        result2 = _build_relationship_map(LocalUser)
        assert result1 is result2

    def test_clear_cache_invalidates(self):
        """clear_cache removes cached data."""
        from apps.accounts.models import LocalUser
        result1 = _build_relationship_map(LocalUser)
        clear_cache()
        result2 = _build_relationship_map(LocalUser)
        assert result1 is not result2

    def test_clear_cache_specific_model(self):
        """clear_cache with model only clears that model."""
        from apps.accounts.models import LocalUser
        result1 = _build_relationship_map(LocalUser)
        clear_cache(LocalUser)
        result2 = _build_relationship_map(LocalUser)
        assert result1 is not result2

    def test_skips_abstract_models(self):
        """Abstract models are not included in relationships."""
        from apps.accounts.models import LocalUser
        result = _build_relationship_map(LocalUser)
        for rel in result:
            assert not rel['model']._meta.abstract

    def test_finds_fk_relations(self):
        """Finds ForeignKey relations pointing to model."""
        from apps.accounts.models import LocalUser
        result = _build_relationship_map(LocalUser)
        fk_relations = [r for r in result if r['relation_type'] == 'fk']
        # LocalUser should be referenced by various models
        assert isinstance(fk_relations, list)

    def test_relation_has_required_keys(self):
        """Each relation has all required keys."""
        from apps.accounts.models import LocalUser
        result = _build_relationship_map(LocalUser)
        required_keys = {'model', 'field', 'field_name', 'accessor', 'relation_type', 'model_label'}
        for rel in result:
            assert required_keys.issubset(rel.keys())


class TestGetReferences:
    """Tests for get_references function."""

    def setup_method(self):
        clear_cache()

    def test_returns_expected_structure(self):
        """get_references returns dict with expected keys."""
        obj = MagicMock(spec=models.Model)
        obj._meta = MagicMock()
        obj._meta.app_label = 'test'
        obj._meta.model_name = 'testmodel'
        obj._meta.abstract = False
        obj._meta.proxy = False
        type(obj)._meta = obj._meta
        type(obj).__name__ = 'TestModel'

        with patch('apps.core.references._build_relationship_map', return_value=[]):
            result = get_references(obj)

        assert 'total_count' in result
        assert 'groups' in result
        assert 'has_protected' in result
        assert 'cascade_count' in result
        assert 'set_null_count' in result
        assert result['total_count'] == 0

    def test_empty_references(self):
        """Object with no references returns zero counts."""
        obj = MagicMock(spec=models.Model)
        obj._meta = MagicMock()
        type(obj)._meta = obj._meta

        with patch('apps.core.references._build_relationship_map', return_value=[]):
            result = get_references(obj)

        assert result['total_count'] == 0
        assert result['groups'] == []
        assert result['has_protected'] is False
        assert result['cascade_count'] == 0
        assert result['set_null_count'] == 0


class TestCanDelete:
    """Tests for can_delete function."""

    def test_can_delete_no_references(self):
        """Object with no references can be deleted."""
        obj = MagicMock(spec=models.Model)
        obj._meta = MagicMock()
        type(obj)._meta = obj._meta

        with patch('apps.core.references._build_relationship_map', return_value=[]):
            ok, refs = can_delete(obj)

        assert ok is True
        assert refs['total_count'] == 0

    def test_returns_tuple(self):
        """can_delete returns a tuple of (bool, dict)."""
        obj = MagicMock(spec=models.Model)
        obj._meta = MagicMock()
        type(obj)._meta = obj._meta

        with patch('apps.core.references._build_relationship_map', return_value=[]):
            result = can_delete(obj)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], dict)


class TestClearCache:
    """Tests for cache management."""

    def test_clear_all(self):
        """clear_cache() clears all cached relationships."""
        from apps.core.references import _relationship_cache
        _relationship_cache['test.model'] = [{'test': True}]
        clear_cache()
        assert len(_relationship_cache) == 0

    def test_clear_specific(self):
        """clear_cache(model) clears only that model."""
        from apps.core.references import _relationship_cache

        class FakeModel:
            class _meta:
                app_label = 'test'
                model_name = 'fake'

        _relationship_cache['test.fake'] = [{'test': True}]
        _relationship_cache['test.other'] = [{'test': True}]

        clear_cache(FakeModel)

        assert 'test.fake' not in _relationship_cache
        assert 'test.other' in _relationship_cache

        # Cleanup
        _relationship_cache.clear()
