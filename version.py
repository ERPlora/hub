"""
CPOS Hub Version Management
Central version file used for app versioning and updates
"""

# Version information
__version__ = '1.0.0'
__version_info__ = tuple(int(x) for x in __version__.split('.'))

# Build information
BUILD_DATE = '2025-01-05'
BUILD_TYPE = 'stable'  # 'stable', 'beta', 'alpha', 'dev'

# Minimum compatible versions
MIN_CLOUD_VERSION = '1.0.0'
MIN_PLUGIN_API_VERSION = '1.0.0'

# Update information
UPDATE_CHECK_URL = 'https://api.cpos.app/hub/updates/check'
DOWNLOAD_URL = 'https://github.com/cpos/hub/releases/latest'


def get_version():
    """Returns the version string"""
    return __version__


def get_version_tuple():
    """Returns the version as a tuple of integers"""
    return __version_info__


def get_full_version():
    """Returns full version with build type"""
    if BUILD_TYPE != 'stable':
        return f'{__version__}-{BUILD_TYPE}'
    return __version__


def get_version_info():
    """Returns complete version information as dict"""
    return {
        'version': __version__,
        'version_tuple': __version_info__,
        'full_version': get_full_version(),
        'build_date': BUILD_DATE,
        'build_type': BUILD_TYPE,
        'min_cloud_version': MIN_CLOUD_VERSION,
        'min_plugin_api_version': MIN_PLUGIN_API_VERSION,
    }


def check_version_compatibility(cloud_version: str) -> bool:
    """
    Check if the Hub version is compatible with Cloud version

    Args:
        cloud_version: Version string from Cloud (e.g., "1.0.0")

    Returns:
        True if compatible, False otherwise
    """
    try:
        cloud_tuple = tuple(int(x) for x in cloud_version.split('.'))
        min_tuple = tuple(int(x) for x in MIN_CLOUD_VERSION.split('.'))
        return cloud_tuple >= min_tuple
    except:
        return False


# Auto-update on import to settings
if __name__ != '__main__':
    import sys
    from pathlib import Path

    # Update settings.py with current version
    settings_file = Path(__file__).parent / 'config' / 'settings.py'
    if settings_file.exists():
        content = settings_file.read_text()
        if 'HUB_VERSION' not in content:
            # Add version to settings if not present
            settings_file.write_text(
                content + f'\n\n# Hub Version\nHUB_VERSION = "{__version__}"\n'
            )
