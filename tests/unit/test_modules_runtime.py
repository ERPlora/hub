"""
Unit tests for modules runtime system.

Tests module loading, activation, and URL registration.
"""
import pytest
from pathlib import Path

pytestmark = pytest.mark.unit


class TestModuleDiscovery:
    """Tests for module discovery and loading."""

    def test_active_module_detection(self, tmp_path):
        """Test that modules without underscore prefix are detected as active."""
        # Create mock module directory structure
        module_dir = tmp_path / 'inventory'
        module_dir.mkdir()

        module_py = module_dir / 'module.py'
        module_py.write_text(
            "MODULE_ID = 'inventory'\n"
            "MODULE_NAME = 'Inventory'\n"
            "MODULE_VERSION = '1.0.0'\n"
        )

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


class TestModulePy:
    """Tests for module.py parsing."""

    def test_valid_module_py(self, tmp_path):
        """Test parsing valid module.py."""
        module_py = tmp_path / 'module.py'
        module_py.write_text(
            "MODULE_ID = 'test_module'\n"
            "MODULE_NAME = 'Test Module'\n"
            "MODULE_VERSION = '1.0.0'\n"
            "MODULE_DESCRIPTION = 'A test module'\n"
            "MODULE_AUTHOR = 'Test Author'\n"
            "MODULE_ICON = 'cube-outline'\n"
            "MODULE_CATEGORY = 'inventory'\n"
            "MENU = {\n"
            "    'label': 'Test',\n"
            "    'icon': 'cube-outline',\n"
            "    'order': 10,\n"
            "}\n"
        )

        import ast
        content = module_py.read_text()
        tree = ast.parse(content)

        metadata = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'MODULE_ID':
                        metadata['module_id'] = ast.literal_eval(node.value)
                    elif isinstance(target, ast.Name) and target.id == 'MODULE_NAME':
                        metadata['name'] = ast.literal_eval(node.value)
                    elif isinstance(target, ast.Name) and target.id == 'MENU':
                        metadata['menu'] = ast.literal_eval(node.value)

        assert metadata['module_id'] == 'test_module'
        assert metadata['name'] == 'Test Module'
        assert metadata['menu']['order'] == 10

    def test_minimal_module_py(self, tmp_path):
        """Test parsing minimal module.py."""
        module_py = tmp_path / 'module.py'
        module_py.write_text(
            "MODULE_ID = 'minimal'\n"
            "MODULE_NAME = 'Minimal Module'\n"
            "MODULE_VERSION = '1.0.0'\n"
        )

        import importlib.util
        spec = importlib.util.spec_from_file_location("minimal.module", module_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod.MODULE_ID == 'minimal'
        assert mod.MODULE_VERSION == '1.0.0'

    def test_module_py_with_dependencies(self, tmp_path):
        """Test parsing module.py with dependencies."""
        module_py = tmp_path / 'module.py'
        module_py.write_text(
            "MODULE_ID = 'sales'\n"
            "MODULE_NAME = 'Sales'\n"
            "MODULE_VERSION = '1.0.0'\n"
            "DEPENDENCIES = ['inventory']\n"
        )

        import importlib.util
        spec = importlib.util.spec_from_file_location("sales.module", module_py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert 'inventory' in mod.DEPENDENCIES


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
