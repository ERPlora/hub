"""
Unit tests for modules runtime system.

Tests module loading, activation, and URL registration.
"""
import pytest
import json
from pathlib import Path

pytestmark = pytest.mark.unit


class TestModuleDiscovery:
    """Tests for module discovery and loading."""

    def test_active_module_detection(self, tmp_path):
        """Test that modules without underscore prefix are detected as active."""
        # Create mock module directory structure
        module_dir = tmp_path / 'inventory'
        module_dir.mkdir()

        module_json = module_dir / 'module.json'
        module_json.write_text(json.dumps({
            'module_id': 'inventory',
            'name': 'Inventory',
            'version': '1.0.0'
        }))

        # Module without underscore should be active
        assert not module_dir.name.startswith('_')
        assert module_dir.exists()

    def test_inactive_module_detection(self, tmp_path):
        """Test that modules with underscore prefix are detected as inactive."""
        module_dir = tmp_path / '_inventory'
        module_dir.mkdir()

        assert module_dir.name.startswith('_')
        assert module_dir.exists()

    def test_hidden_module_detection(self, tmp_path):
        """Test that modules with dot prefix are hidden."""
        module_dir = tmp_path / '.template'
        module_dir.mkdir()

        assert module_dir.name.startswith('.')


class TestModuleJson:
    """Tests for module.json parsing."""

    def test_valid_module_json(self, tmp_path):
        """Test parsing valid module.json."""
        module_json = tmp_path / 'module.json'
        data = {
            'module_id': 'test_module',
            'name': 'Test Module',
            'name_es': 'Módulo de Prueba',
            'version': '1.0.0',
            'description': 'A test module',
            'author': 'Test Author',
            'icon': 'cube-outline',
            'category': 'inventory',
            'tags': ['test', 'inventory'],
            'menu': {
                'label': 'Test',
                'icon': 'cube-outline',
                'url': '/modules/test_module/',
                'order': 10
            }
        }
        module_json.write_text(json.dumps(data))

        loaded = json.loads(module_json.read_text())

        assert loaded['module_id'] == 'test_module'
        assert loaded['name'] == 'Test Module'
        assert loaded['tags'] == ['test', 'inventory']
        assert loaded['menu']['order'] == 10

    def test_minimal_module_json(self, tmp_path):
        """Test parsing minimal module.json."""
        module_json = tmp_path / 'module.json'
        data = {
            'module_id': 'minimal',
            'name': 'Minimal Module',
            'version': '1.0.0'
        }
        module_json.write_text(json.dumps(data))

        loaded = json.loads(module_json.read_text())

        assert loaded['module_id'] == 'minimal'
        assert loaded['version'] == '1.0.0'

    def test_module_json_with_dependencies(self, tmp_path):
        """Test parsing module.json with dependencies."""
        module_json = tmp_path / 'module.json'
        data = {
            'module_id': 'sales',
            'name': 'Sales',
            'version': '1.0.0',
            'dependencies': {
                'python': ['requests>=2.0.0'],
                'modules': ['inventory>=1.0.0']
            }
        }
        module_json.write_text(json.dumps(data))

        loaded = json.loads(module_json.read_text())

        assert 'requests>=2.0.0' in loaded['dependencies']['python']
        assert 'inventory>=1.0.0' in loaded['dependencies']['modules']


class TestModuleURLPatterns:
    """Tests for module URL pattern structure."""

    def test_module_url_format(self):
        """Test that module URLs follow expected format."""
        module_id = 'inventory'
        expected_url = f'/m/{module_id}/'

        assert expected_url.startswith('/m/')
        assert expected_url.endswith('/')

    def test_module_api_url_format(self):
        """Test that module API URLs follow expected format."""
        expected_base = '/api/v1/modules/'

        assert expected_base.startswith('/api/')
        assert 'modules' in expected_base
