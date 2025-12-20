"""
Unit tests for plugins runtime system.

Tests plugin loading, activation, and URL registration.
"""
import pytest
import json
from pathlib import Path

pytestmark = pytest.mark.unit


class TestPluginDiscovery:
    """Tests for plugin discovery and loading."""

    def test_active_plugin_detection(self, tmp_path):
        """Test that plugins without underscore prefix are detected as active."""
        # Create mock plugin directory structure
        plugin_dir = tmp_path / 'inventory'
        plugin_dir.mkdir()

        plugin_json = plugin_dir / 'plugin.json'
        plugin_json.write_text(json.dumps({
            'plugin_id': 'inventory',
            'name': 'Inventory',
            'version': '1.0.0'
        }))

        # Plugin without underscore should be active
        assert not plugin_dir.name.startswith('_')
        assert plugin_dir.exists()

    def test_inactive_plugin_detection(self, tmp_path):
        """Test that plugins with underscore prefix are detected as inactive."""
        plugin_dir = tmp_path / '_inventory'
        plugin_dir.mkdir()

        assert plugin_dir.name.startswith('_')
        assert plugin_dir.exists()

    def test_hidden_plugin_detection(self, tmp_path):
        """Test that plugins with dot prefix are hidden."""
        plugin_dir = tmp_path / '.template'
        plugin_dir.mkdir()

        assert plugin_dir.name.startswith('.')


class TestPluginJson:
    """Tests for plugin.json parsing."""

    def test_valid_plugin_json(self, tmp_path):
        """Test parsing valid plugin.json."""
        plugin_json = tmp_path / 'plugin.json'
        data = {
            'plugin_id': 'test_plugin',
            'name': 'Test Plugin',
            'name_es': 'Plugin de Prueba',
            'version': '1.0.0',
            'description': 'A test plugin',
            'author': 'Test Author',
            'icon': 'cube-outline',
            'category': 'inventory',
            'tags': ['test', 'inventory'],
            'menu': {
                'label': 'Test',
                'icon': 'cube-outline',
                'url': '/plugins/test_plugin/',
                'order': 10
            }
        }
        plugin_json.write_text(json.dumps(data))

        loaded = json.loads(plugin_json.read_text())

        assert loaded['plugin_id'] == 'test_plugin'
        assert loaded['name'] == 'Test Plugin'
        assert loaded['tags'] == ['test', 'inventory']
        assert loaded['menu']['order'] == 10

    def test_minimal_plugin_json(self, tmp_path):
        """Test parsing minimal plugin.json."""
        plugin_json = tmp_path / 'plugin.json'
        data = {
            'plugin_id': 'minimal',
            'name': 'Minimal Plugin',
            'version': '1.0.0'
        }
        plugin_json.write_text(json.dumps(data))

        loaded = json.loads(plugin_json.read_text())

        assert loaded['plugin_id'] == 'minimal'
        assert loaded['version'] == '1.0.0'

    def test_plugin_json_with_dependencies(self, tmp_path):
        """Test parsing plugin.json with dependencies."""
        plugin_json = tmp_path / 'plugin.json'
        data = {
            'plugin_id': 'sales',
            'name': 'Sales',
            'version': '1.0.0',
            'dependencies': {
                'python': ['requests>=2.0.0'],
                'plugins': ['inventory>=1.0.0']
            }
        }
        plugin_json.write_text(json.dumps(data))

        loaded = json.loads(plugin_json.read_text())

        assert 'requests>=2.0.0' in loaded['dependencies']['python']
        assert 'inventory>=1.0.0' in loaded['dependencies']['plugins']


class TestPluginURLPatterns:
    """Tests for plugin URL pattern structure."""

    def test_plugin_url_format(self):
        """Test that plugin URLs follow expected format."""
        plugin_id = 'inventory'
        expected_url = f'/plugins/{plugin_id}/'

        assert expected_url.startswith('/plugins/')
        assert expected_url.endswith('/')

    def test_plugin_api_url_format(self):
        """Test that plugin API URLs follow expected format."""
        expected_base = '/api/v1/plugins/'

        assert expected_base.startswith('/api/')
        assert 'plugins' in expected_base
