"""
Unit tests for config/paths.py - Data paths management

Tests the cross-platform path management system that handles
external data storage for database, media, plugins, etc.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from config.paths import DataPaths, get_data_paths


@pytest.mark.unit
class TestDataPathsInitialization:
    """Test DataPaths class initialization"""

    def test_creates_instance(self):
        """Should create DataPaths instance"""
        # Use real DataPaths but it will create dirs in real locations
        # This is OK for this basic test
        paths = DataPaths()
        assert paths is not None
        assert isinstance(paths, DataPaths)

    def test_detects_platform(self):
        """Should detect current platform"""
        paths = DataPaths()
        assert paths.platform in ['win32', 'darwin', 'linux']

    def test_creates_directories_on_init(self):
        """Should create all required directories on initialization"""
        # DataPaths creates directories in OS-specific locations (external to project)
        # These are the actual directories the app will use in production
        paths = DataPaths()
        # All directories should exist
        assert paths.base_dir.exists()
        assert paths.database_dir.exists()
        assert paths.media_dir.exists()
        assert paths.plugins_dir.exists()
        assert paths.reports_dir.exists()
        assert paths.logs_dir.exists()
        assert paths.backups_dir.exists()
        assert paths.temp_dir.exists()


@pytest.mark.unit
class TestDataPathsBaseDirPlatformSpecific:
    """Test base_dir property for different platforms"""

    def test_base_dir_current_platform(self):
        """Should return correct path for current platform"""
        paths = DataPaths()
        base_str = str(paths.base_dir)

        # Verify path contains expected components for current platform
        assert 'ERPloraHub' in base_str or '.cpos-hub' in base_str

        # Platform-specific checks
        if paths.platform == 'darwin':
            assert 'Library/Application Support' in base_str or 'Library' in base_str
        elif paths.platform == 'linux':
            assert '.cpos-hub' in base_str
        elif paths.platform == 'win32':
            assert 'AppData' in base_str or 'ERPloraHub' in base_str

    # NOTE: Cross-platform mocking tests removed because they created
    # directories in the project (e.g., ./C:/Users/...).
    # Testing DataPaths on actual OS is sufficient for unit tests.
    # Integration tests can use Docker containers for multi-platform testing.


@pytest.mark.unit
class TestDataPathsSubdirectories:
    """Test subdirectory properties"""

    def test_database_dir(self):
        """Should return database directory"""
        paths = DataPaths()
        assert paths.database_dir == paths.base_dir / 'db'

    def test_database_path(self):
        """Should return full path to db.sqlite3"""
        paths = DataPaths()
        expected = paths.base_dir / 'db' / 'db.sqlite3'
        assert paths.database_path == expected

    def test_media_dir(self):
        """Should return media directory"""
        paths = DataPaths()
        assert paths.media_dir == paths.base_dir / 'media'

    def test_plugins_dir(self):
        """Should return plugins directory"""
        paths = DataPaths()
        assert paths.plugins_dir == paths.base_dir / 'plugins'

    def test_reports_dir(self):
        """Should return reports directory"""
        paths = DataPaths()
        assert paths.reports_dir == paths.base_dir / 'reports'

    def test_logs_dir(self):
        """Should return logs directory"""
        paths = DataPaths()
        assert paths.logs_dir == paths.base_dir / 'logs'

    def test_backups_dir(self):
        """Should return backups directory"""
        paths = DataPaths()
        assert paths.backups_dir == paths.base_dir / 'backups'

    def test_temp_dir(self):
        """Should return temp directory"""
        paths = DataPaths()
        assert paths.temp_dir == paths.base_dir / 'temp'


@pytest.mark.unit
class TestDataPathsGetAllPaths:
    """Test get_all_paths() method"""

    def test_returns_dict(self):
        """Should return dictionary of all paths"""
        paths = DataPaths()
        all_paths = paths.get_all_paths()
        assert isinstance(all_paths, dict)

    def test_contains_all_keys(self):
        """Should contain all expected keys"""
        paths = DataPaths()
        all_paths = paths.get_all_paths()
        expected_keys = {
            'base', 'database', 'database_dir', 'media',
            'plugins', 'reports', 'logs', 'backups', 'temp'
        }
        assert set(all_paths.keys()) == expected_keys

    def test_all_values_are_paths(self):
        """Should have Path objects as values"""
        paths = DataPaths()
        all_paths = paths.get_all_paths()
        for value in all_paths.values():
            assert isinstance(value, Path)


@pytest.mark.unit
class TestDataPathsPluginPaths:
    """Test plugin-specific path methods"""

    def test_get_plugin_data_dir(self):
        """Should return plugin data directory"""
        paths = DataPaths()
        plugin_data = paths.get_plugin_data_dir('test-plugin')
        expected = paths.plugins_dir / 'test-plugin' / 'data'
        assert plugin_data == expected

    def test_get_plugin_data_dir_creates_directory(self):
        """Should create plugin data directory if not exists"""
        paths = DataPaths()
        plugin_data = paths.get_plugin_data_dir('new-plugin')
        assert plugin_data.exists()
        assert plugin_data.is_dir()

    def test_get_plugin_media_dir(self):
        """Should return plugin media directory"""
        paths = DataPaths()
        plugin_media = paths.get_plugin_media_dir('test-plugin')
        expected = paths.media_dir / 'plugins' / 'test-plugin'
        assert plugin_media == expected

    def test_get_plugin_media_dir_creates_directory(self):
        """Should create plugin media directory if not exists"""
        paths = DataPaths()
        plugin_media = paths.get_plugin_media_dir('new-plugin')
        assert plugin_media.exists()
        assert plugin_media.is_dir()


@pytest.mark.unit
class TestDataPathsCleanupTemp:
    """Test cleanup_temp() method"""

    def test_removes_temp_contents(self):
        """Should remove all contents of temp directory"""
        paths = DataPaths()
        # Create test file in temp
        test_file = paths.temp_dir / 'test.txt'
        test_file.write_text('test content')
        assert test_file.exists()

        # Cleanup
        paths.cleanup_temp()

        # Temp dir should exist but be empty
        assert paths.temp_dir.exists()
        assert not test_file.exists()

    def test_recreates_temp_directory(self):
        """Should recreate temp directory after cleanup"""
        paths = DataPaths()
        paths.cleanup_temp()
        assert paths.temp_dir.exists()
        assert paths.temp_dir.is_dir()


@pytest.mark.unit
class TestDataPathsModuleFunctions:
    """Test module-level functions"""

    def test_get_data_paths_returns_singleton(self):
        """Should return same DataPaths instance"""
        paths1 = get_data_paths()
        paths2 = get_data_paths()
        assert paths1 is paths2

    def test_get_data_paths_returns_datapaths(self):
        """Should return DataPaths instance"""
        paths = get_data_paths()
        assert isinstance(paths, DataPaths)


@pytest.mark.unit
class TestDataPathsRepr:
    """Test __repr__() method"""

    def test_repr_format(self):
        """Should return formatted string representation"""
        paths = DataPaths()
        repr_str = repr(paths)
        assert repr_str.startswith('<DataPaths')
        assert 'platform=' in repr_str
        assert 'base=' in repr_str
