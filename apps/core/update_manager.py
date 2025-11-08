"""
Update Manager for CPOS Hub

Handles version checking, downloading, and installing updates from the Cloud.
Includes automatic backup and rollback functionality.
"""

import os
import sys
import json
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime
import requests
import logging
from packaging import version
from django.conf import settings

logger = logging.getLogger(__name__)


class UpdateState:
    """
    Represents the current state of an update operation.
    """
    CHECKING = 'checking'
    AVAILABLE = 'available'
    DOWNLOADING = 'downloading'
    DOWNLOADED = 'downloaded'
    INSTALLING = 'installing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    ROLLED_BACK = 'rolled_back'


class UpdateManager:
    """
    Manages Hub software updates.

    Features:
    - Version checking against Cloud API
    - Download of new versions
    - Automatic backup before update
    - Installation of updates
    - Rollback on failure
    """

    def __init__(self):
        # Base directory for Hub (where manage.py lives)
        self.hub_dir = Path(settings.BASE_DIR)

        # Temporary directory for downloads
        self.temp_dir = Path(tempfile.gettempdir()) / 'cpos_hub_updates'
        self.temp_dir.mkdir(exist_ok=True)

        # Backup directory
        self.backup_dir = self.hub_dir / 'backups'
        self.backup_dir.mkdir(exist_ok=True)

        # Update state file
        self.state_file = self.hub_dir / 'update_state.json'

        # Cloud API URL
        self.cloud_api_url = getattr(
            settings,
            'CLOUD_API_URL',
            'https://cpos.app/api/hubs'
        )

        # Current version
        self.current_version = self._get_current_version()

        # Current OS
        self.os_type = self._detect_os()

    def _get_current_version(self) -> str:
        """
        Get the current version of CPOS Hub.

        Returns:
            str: Version string (e.g., "1.0.0")
        """
        try:
            # Try to get version from package metadata
            from importlib.metadata import version as get_version
            return get_version('cpos-hub')
        except Exception:
            # Fallback to pyproject.toml
            try:
                import tomllib
                pyproject_path = self.hub_dir / 'pyproject.toml'

                if pyproject_path.exists():
                    with open(pyproject_path, 'rb') as f:
                        pyproject = tomllib.load(f)
                        return pyproject.get('project', {}).get('version', '0.0.0')
            except Exception as e:
                logger.warning(f"Could not read version from pyproject.toml: {e}")

        # Ultimate fallback
        return '0.0.0'

    def _detect_os(self) -> str:
        """
        Detect the current operating system.

        Returns:
            str: 'windows', 'macos', or 'linux'
        """
        if sys.platform == 'win32':
            return 'windows'
        elif sys.platform == 'darwin':
            return 'macos'
        else:
            return 'linux'

    def check_for_updates(self) -> Dict:
        """
        Check if a new version is available from the Cloud.

        Returns:
            dict: {
                'update_available': bool,
                'current_version': str,
                'latest_version': str,
                'update_type': str,  # 'major', 'minor', or 'patch'
                'release_notes': str,
                'download_url': str,
                'file_size_mb': int,
                'mandatory': bool,
                'error': str (if failed)
            }
        """
        result = {
            'update_available': False,
            'current_version': self.current_version,
            'latest_version': None,
            'update_type': None,
            'release_notes': None,
            'download_url': None,
            'file_size_mb': None,
            'mandatory': False,
            'error': None,
        }

        try:
            # Call Cloud API to check version
            url = f"{self.cloud_api_url}/version/check/"
            params = {
                'current_version': self.current_version,
                'os': self.os_type,
            }

            logger.info(f"Checking for updates: {url} (current: {self.current_version}, os: {self.os_type})")

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Update result with API response
            result.update({
                'update_available': data.get('update_available', False),
                'latest_version': data.get('latest_version'),
                'update_type': data.get('update_type'),
                'release_notes': data.get('release_notes'),
                'download_url': data.get('download_url'),
                'file_size_mb': data.get('file_size_mb'),
                'mandatory': data.get('mandatory', False),
            })

            # Save state
            self._save_state({
                'last_check': datetime.now().isoformat(),
                'update_available': result['update_available'],
                'latest_version': result['latest_version'],
                'current_version': self.current_version,
            })

            if result['update_available']:
                logger.info(
                    f"Update available: {self.current_version} -> {result['latest_version']} "
                    f"({result['update_type']})"
                )
            else:
                logger.info(f"Already on latest version: {self.current_version}")

            return result

        except requests.RequestException as e:
            error_msg = f"Network error checking for updates: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            return result

        except Exception as e:
            error_msg = f"Error checking for updates: {str(e)}"
            logger.exception(error_msg)
            result['error'] = error_msg
            return result

    def download_update(self, download_url: str, target_version: str) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Download an update file from the given URL.

        Args:
            download_url: URL to download the update from
            target_version: Version being downloaded (e.g., "1.2.0")

        Returns:
            Tuple[bool, Optional[Path], Optional[str]]:
                (success, file_path, error_message)
        """
        try:
            logger.info(f"Downloading update {target_version} from {download_url}")

            # Determine file extension
            if self.os_type == 'linux' and download_url.endswith('.tar.gz'):
                ext = '.tar.gz'
            else:
                ext = '.zip'

            # Create download path
            filename = f"cpos_hub_update_{target_version}{ext}"
            download_path = self.temp_dir / filename

            # Download with progress tracking
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Log progress every 10MB
                        if downloaded % (10 * 1024 * 1024) == 0:
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                logger.info(f"Download progress: {progress:.1f}%")

            logger.info(f"Download completed: {download_path} ({downloaded / 1024 / 1024:.1f} MB)")

            # TODO: Verify checksum/signature

            return True, download_path, None

        except requests.RequestException as e:
            error_msg = f"Network error downloading update: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

        except Exception as e:
            error_msg = f"Error downloading update: {str(e)}"
            logger.exception(error_msg)
            return False, None, error_msg

    def create_backup(self, backup_name: Optional[str] = None) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Create a backup of the current Hub installation.

        Args:
            backup_name: Optional custom name for backup

        Returns:
            Tuple[bool, Optional[Path], Optional[str]]:
                (success, backup_path, error_message)
        """
        try:
            if not backup_name:
                backup_name = f"backup_{self.current_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            backup_path = self.backup_dir / backup_name
            backup_path.mkdir(exist_ok=True)

            logger.info(f"Creating backup: {backup_path}")

            # Backup SQLite database
            db_path = self._get_database_path()
            if db_path and db_path.exists():
                shutil.copy2(db_path, backup_path / 'db.sqlite3')
                logger.info(f"Backed up database: {db_path}")

            # Backup plugins directory
            plugins_dir = self.hub_dir / 'plugins'
            if plugins_dir.exists():
                shutil.copytree(
                    plugins_dir,
                    backup_path / 'plugins',
                    dirs_exist_ok=True
                )
                logger.info(f"Backed up plugins: {plugins_dir}")

            # Backup configuration files
            config_files = ['config.json', '.env', 'hub_config.json']
            for config_file in config_files:
                config_path = self.hub_dir / config_file
                if config_path.exists():
                    shutil.copy2(config_path, backup_path / config_file)
                    logger.info(f"Backed up config: {config_file}")

            # Save backup metadata
            metadata = {
                'version': self.current_version,
                'created_at': datetime.now().isoformat(),
                'os': self.os_type,
            }
            with open(backup_path / 'backup_metadata.json', 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Backup created successfully: {backup_path}")
            return True, backup_path, None

        except Exception as e:
            error_msg = f"Error creating backup: {str(e)}"
            logger.exception(error_msg)
            return False, None, error_msg

    def _get_database_path(self) -> Optional[Path]:
        """Get the path to the SQLite database."""
        try:
            from django.db import connections
            db_path = connections['default'].settings_dict.get('NAME')
            if db_path:
                return Path(db_path)
        except Exception as e:
            logger.warning(f"Could not get database path: {e}")
        return None

    def _save_state(self, state: Dict):
        """Save update state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save update state: {e}")

    def get_state(self) -> Optional[Dict]:
        """Load update state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load update state: {e}")
        return None

    def verify_download(self, file_path: Path, expected_checksum: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Verify integrity of downloaded file using SHA256 checksum.

        Args:
            file_path: Path to downloaded file
            expected_checksum: Expected SHA256 checksum (optional)

        Returns:
            Tuple[bool, Optional[str]]: (is_valid, error_message)
        """
        try:
            import hashlib

            logger.info(f"Verifying download: {file_path}")

            if not file_path.exists():
                return False, "File does not exist"

            # Calculate SHA256 checksum
            sha256_hash = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)

            actual_checksum = sha256_hash.hexdigest()
            logger.info(f"Calculated checksum: {actual_checksum}")

            # If expected checksum provided, verify it
            if expected_checksum:
                if actual_checksum != expected_checksum:
                    error_msg = f"Checksum mismatch! Expected: {expected_checksum}, Got: {actual_checksum}"
                    logger.error(error_msg)
                    return False, error_msg
                else:
                    logger.info("✅ Checksum verification passed")

            return True, None

        except Exception as e:
            error_msg = f"Error verifying download: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

    def install_update(self, update_file: Path, target_version: str, backup_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Install an update from a downloaded file.

        This extracts the update and prepares it for installation.
        The actual replacement happens via a separate updater script that runs
        after the Hub process exits.

        Args:
            update_file: Path to downloaded update file
            target_version: Version being installed
            backup_path: Path to backup directory (for rollback)

        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        try:
            logger.info(f"Installing update {target_version} from {update_file}")

            # Create extraction directory
            extract_dir = self.temp_dir / f"extract_{target_version}"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True)

            # Extract update file
            logger.info(f"Extracting update to: {extract_dir}")

            if update_file.suffix == '.zip':
                with zipfile.ZipFile(update_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            elif update_file.name.endswith('.tar.gz'):
                import tarfile
                with tarfile.open(update_file, 'r:gz') as tar_ref:
                    tar_ref.extractall(extract_dir)
            else:
                return False, f"Unsupported file format: {update_file.suffix}"

            logger.info("Extraction completed")

            # Run database migrations if needed
            migration_success = self._run_migrations_for_update(extract_dir)
            if not migration_success:
                logger.warning("Migrations failed or skipped")

            # Create updater script to replace files after Hub exits
            updater_script = self._create_updater_script(
                extract_dir,
                target_version,
                backup_path
            )

            if not updater_script:
                return False, "Failed to create updater script"

            logger.info(f"✅ Update prepared successfully: {updater_script}")

            # Save state for post-update verification
            self._save_state({
                'update_in_progress': True,
                'target_version': target_version,
                'backup_path': str(backup_path),
                'updater_script': str(updater_script),
                'started_at': datetime.now().isoformat(),
            })

            return True, None

        except Exception as e:
            error_msg = f"Error installing update: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

    def _run_migrations_for_update(self, extract_dir: Path) -> bool:
        """
        Run Django migrations from the extracted update.

        Args:
            extract_dir: Directory where update was extracted

        Returns:
            bool: True if migrations successful or skipped, False if failed
        """
        try:
            # Check if there are new migration files
            # This is a simplified version - in production you'd want to:
            # 1. Compare migration files between current and new version
            # 2. Run only new migrations
            # 3. Handle migration dependencies

            logger.info("Checking for database migrations...")

            # For now, we'll skip automatic migration during update
            # Migrations will run when the new version starts
            logger.info("Migrations will be applied on next startup")

            return True

        except Exception as e:
            logger.exception(f"Error running migrations: {e}")
            return False

    def _create_updater_script(self, extract_dir: Path, target_version: str, backup_path: Path) -> Optional[Path]:
        """
        Create a platform-specific updater script.

        The script will:
        1. Wait for Hub to exit
        2. Replace Hub files with new version
        3. Restart Hub
        4. If restart fails, rollback to backup

        Args:
            extract_dir: Directory with extracted update files
            target_version: Version being installed
            backup_path: Path to backup for rollback

        Returns:
            Optional[Path]: Path to updater script or None if failed
        """
        try:
            if self.os_type == 'windows':
                return self._create_windows_updater(extract_dir, target_version, backup_path)
            elif self.os_type == 'macos':
                return self._create_macos_updater(extract_dir, target_version, backup_path)
            else:  # linux
                return self._create_linux_updater(extract_dir, target_version, backup_path)

        except Exception as e:
            logger.exception(f"Error creating updater script: {e}")
            return None

    def _create_windows_updater(self, extract_dir: Path, target_version: str, backup_path: Path) -> Optional[Path]:
        """Create Windows batch script for update installation."""
        script_path = self.temp_dir / f"updater_{target_version}.bat"

        # Get the Hub installation directory
        if getattr(sys, 'frozen', False):
            # Running from PyInstaller bundle
            install_dir = Path(sys.executable).parent
        else:
            # Development mode
            install_dir = self.hub_dir

        script_content = f"""@echo off
REM CPOS Hub Updater Script - Windows
REM Version: {target_version}

echo ========================================
echo CPOS Hub Update Installer
echo Updating to version {target_version}
echo ========================================
echo.

REM Wait for Hub to exit (5 seconds)
echo Waiting for Hub to close...
timeout /t 5 /nobreak >nul

REM Backup current installation (additional safety)
echo Creating safety backup...
xcopy "{install_dir}" "{backup_path}_safety" /E /I /H /Y >nul

REM Replace files with new version
echo Installing new version...
xcopy "{extract_dir}\\*" "{install_dir}" /E /I /H /Y

if errorlevel 1 (
    echo.
    echo [ERROR] Installation failed! Rolling back...
    xcopy "{backup_path}_safety\\*" "{install_dir}" /E /I /H /Y
    echo Rollback completed.
    pause
    exit /b 1
)

echo.
echo ========================================
echo Update installed successfully!
echo ========================================
echo.

REM Restart Hub
echo Restarting CPOS Hub...
start "" "{install_dir}\\main.exe"

REM Clean up
timeout /t 3 /nobreak >nul
rmdir /s /q "{extract_dir}"
rmdir /s /q "{backup_path}_safety"

exit /b 0
"""

        with open(script_path, 'w') as f:
            f.write(script_content)

        logger.info(f"Created Windows updater script: {script_path}")
        return script_path

    def _create_macos_updater(self, extract_dir: Path, target_version: str, backup_path: Path) -> Optional[Path]:
        """Create macOS shell script for update installation."""
        script_path = self.temp_dir / f"updater_{target_version}.sh"

        # Get the Hub installation directory (.app bundle)
        if getattr(sys, 'frozen', False):
            # Running from PyInstaller bundle
            # Path is like: /Applications/CPOS Hub.app/Contents/MacOS/main
            install_dir = Path(sys.executable).parent.parent.parent
        else:
            # Development mode
            install_dir = self.hub_dir

        script_content = f"""#!/bin/bash
# CPOS Hub Updater Script - macOS
# Version: {target_version}

set -e  # Exit on error

echo "========================================"
echo "CPOS Hub Update Installer"
echo "Updating to version {target_version}"
echo "========================================"
echo

# Wait for Hub to exit
echo "Waiting for Hub to close..."
sleep 5

# Backup current installation (additional safety)
echo "Creating safety backup..."
cp -R "{install_dir}" "{backup_path}_safety"

# Replace files with new version
echo "Installing new version..."
rm -rf "{install_dir}"
cp -R "{extract_dir}/CPOS Hub.app" "{install_dir}"

if [ $? -ne 0 ]; then
    echo
    echo "[ERROR] Installation failed! Rolling back..."
    rm -rf "{install_dir}"
    cp -R "{backup_path}_safety" "{install_dir}"
    echo "Rollback completed."
    exit 1
fi

echo
echo "========================================"
echo "Update installed successfully!"
echo "========================================"
echo

# Restart Hub
echo "Restarting CPOS Hub..."
open "{install_dir}"

# Clean up
sleep 3
rm -rf "{extract_dir}"
rm -rf "{backup_path}_safety"

exit 0
"""

        with open(script_path, 'w') as f:
            f.write(script_content)

        # Make script executable
        os.chmod(script_path, 0o755)

        logger.info(f"Created macOS updater script: {script_path}")
        return script_path

    def _create_linux_updater(self, extract_dir: Path, target_version: str, backup_path: Path) -> Optional[Path]:
        """Create Linux shell script for update installation."""
        script_path = self.temp_dir / f"updater_{target_version}.sh"

        # Get the Hub installation directory
        if getattr(sys, 'frozen', False):
            # Running from PyInstaller bundle
            install_dir = Path(sys.executable).parent
        else:
            # Development mode
            install_dir = self.hub_dir

        script_content = f"""#!/bin/bash
# CPOS Hub Updater Script - Linux
# Version: {target_version}

set -e  # Exit on error

echo "========================================"
echo "CPOS Hub Update Installer"
echo "Updating to version {target_version}"
echo "========================================"
echo

# Wait for Hub to exit
echo "Waiting for Hub to close..."
sleep 5

# Backup current installation (additional safety)
echo "Creating safety backup..."
cp -R "{install_dir}" "{backup_path}_safety"

# Replace files with new version
echo "Installing new version..."
rm -rf "{install_dir}"/*
cp -R "{extract_dir}"/* "{install_dir}"/

if [ $? -ne 0 ]; then
    echo
    echo "[ERROR] Installation failed! Rolling back..."
    rm -rf "{install_dir}"/*
    cp -R "{backup_path}_safety"/* "{install_dir}"/
    echo "Rollback completed."
    exit 1
fi

echo
echo "========================================"
echo "Update installed successfully!"
echo "========================================"
echo

# Restart Hub
echo "Restarting CPOS Hub..."
cd "{install_dir}"
./main &

# Clean up
sleep 3
rm -rf "{extract_dir}"
rm -rf "{backup_path}_safety"

exit 0
"""

        with open(script_path, 'w') as f:
            f.write(script_content)

        # Make script executable
        os.chmod(script_path, 0o755)

        logger.info(f"Created Linux updater script: {script_path}")
        return script_path

    def apply_update(self) -> Tuple[bool, Optional[str]]:
        """
        Execute the updater script and exit the Hub.

        This should be called when the user confirms they want to install the update.
        The Hub will exit and the updater script will replace the files.

        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        try:
            state = self.get_state()

            if not state or not state.get('update_in_progress'):
                return False, "No update in progress"

            updater_script = state.get('updater_script')
            if not updater_script or not Path(updater_script).exists():
                return False, "Updater script not found"

            logger.info(f"Applying update via script: {updater_script}")

            # Execute updater script in background
            if self.os_type == 'windows':
                # Windows: Use subprocess.Popen with detached process
                subprocess.Popen(
                    ['cmd', '/c', str(updater_script)],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    close_fds=True
                )
            else:
                # Unix: Use nohup to detach from parent process
                subprocess.Popen(
                    ['nohup', 'sh', str(updater_script)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setpgrp,  # Detach from process group
                    close_fds=True
                )

            logger.info("✅ Updater script started. Hub will now exit.")

            # Exit the Hub to allow updater to replace files
            # Django will handle shutdown gracefully
            os._exit(0)

        except Exception as e:
            error_msg = f"Error applying update: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg

    def rollback_update(self, backup_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Rollback to a previous backup.

        Args:
            backup_path: Path to backup directory

        Returns:
            Tuple[bool, Optional[str]]: (success, error_message)
        """
        try:
            logger.info(f"Rolling back to backup: {backup_path}")

            if not backup_path.exists():
                return False, f"Backup not found: {backup_path}"

            # Restore database
            db_backup = backup_path / 'db.sqlite3'
            if db_backup.exists():
                db_path = self._get_database_path()
                if db_path:
                    shutil.copy2(db_backup, db_path)
                    logger.info(f"Restored database from backup")

            # Restore plugins
            plugins_backup = backup_path / 'plugins'
            if plugins_backup.exists():
                plugins_dir = self.hub_dir / 'plugins'
                if plugins_dir.exists():
                    shutil.rmtree(plugins_dir)
                shutil.copytree(plugins_backup, plugins_dir)
                logger.info(f"Restored plugins from backup")

            # Restore configuration files
            for config_file in ['config.json', '.env', 'hub_config.json']:
                config_backup = backup_path / config_file
                if config_backup.exists():
                    shutil.copy2(config_backup, self.hub_dir / config_file)
                    logger.info(f"Restored config: {config_file}")

            logger.info("✅ Rollback completed successfully")

            # Clear update state
            self._save_state({
                'update_in_progress': False,
                'last_rollback': datetime.now().isoformat(),
                'rolled_back_from': backup_path.name,
            })

            return True, None

        except Exception as e:
            error_msg = f"Error during rollback: {str(e)}"
            logger.exception(error_msg)
            return False, error_msg


# Global instance
update_manager = UpdateManager()
