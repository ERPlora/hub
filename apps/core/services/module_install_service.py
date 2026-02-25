"""
Module Install Service for ERPlora Hub.

Centralizes all module download/install logic. Used by:
- Setup wizard (batch install from functional blocks)
- Marketplace UI (single module install)
- REST API (single module install)
- Legacy views (backward compat)
"""

import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import requests as http_requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    success: bool
    module_id: str
    message: str


@dataclass
class BulkInstallResult:
    installed: int
    errors: list = field(default_factory=list)
    results: list = field(default_factory=list)


class ModuleInstallService:
    """
    Centralized service for downloading and installing modules.

    All module installs go through download_and_install() which handles:
    - Authenticated download with X-Hub-Token
    - ZIP extraction with single-root-folder detection
    - MODULE_ID discovery from module.py
    - Copy to MODULES_DIR with already-installed check
    """

    @classmethod
    def get_hub_token(cls, hub_config=None):
        """Resolve hub_token from HubConfig or settings.

        Priority: hub_config.hub_jwt → settings.HUB_JWT
        """
        token = ''
        if hub_config:
            token = getattr(hub_config, 'hub_jwt', '') or ''
        if not token:
            try:
                from apps.configuration.models import HubConfig
                config = HubConfig.get_solo()
                token = config.hub_jwt or ''
            except Exception:
                pass
        if not token:
            token = getattr(settings, 'HUB_JWT', '') or ''
        return token

    @classmethod
    def get_cloud_url(cls):
        """Get the Cloud API base URL from settings."""
        return getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')

    @classmethod
    def download_and_install(cls, module_slug, download_url, hub_token=''):
        """Download a module ZIP from URL, extract, and install to MODULES_DIR.

        This is the single canonical install path. Does NOT perform post-install
        steps (load, migrate, restart) — call run_post_install() separately.

        Args:
            module_slug: Module slug/identifier (used as fallback for module_id)
            download_url: URL to download the module ZIP from
            hub_token: Hub JWT token for authentication

        Returns:
            InstallResult with success status, resolved module_id, and message
        """
        modules_dir = Path(settings.MODULES_DIR)

        # Normalize URL
        if download_url.startswith('http://'):
            download_url = download_url.replace('http://', 'https://', 1)

        # Build auth headers
        headers = {}
        if hub_token:
            headers['X-Hub-Token'] = hub_token

        # Download
        try:
            resp = http_requests.get(
                download_url, headers=headers, timeout=120, stream=True
            )
            if resp.status_code != 200:
                logger.warning(
                    "[INSTALL] Download HTTP %d: %s", resp.status_code, download_url
                )
                return InstallResult(
                    success=False,
                    module_id=module_slug,
                    message=f"Download failed: HTTP {resp.status_code}",
                )
            resp.raise_for_status()
        except http_requests.exceptions.RequestException as e:
            logger.warning("[INSTALL] Download error: %s - %s", download_url, e)
            return InstallResult(
                success=False, module_id=module_slug, message=f"Download failed: {e}"
            )

        # Save to temp file and extract
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
                for chunk in resp.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = tmp.name

            with tempfile.TemporaryDirectory() as tmp_extract:
                tmp_extract_path = Path(tmp_extract)

                with zipfile.ZipFile(tmp_path, 'r') as zf:
                    zf.extractall(tmp_extract_path)

                # Detect single root folder
                items = list(tmp_extract_path.iterdir())
                if len(items) == 1 and items[0].is_dir():
                    extracted_root = items[0]
                else:
                    extracted_root = tmp_extract_path

                # Discover MODULE_ID from module.py
                module_id = cls._get_module_id_from_extracted(
                    extracted_root, module_slug
                )

                # Check if already installed
                target = modules_dir / module_id
                if target.exists() or (modules_dir / f"_{module_id}").exists():
                    return InstallResult(
                        success=True,
                        module_id=module_id,
                        message=f"{module_id} already installed",
                    )

                # Copy to modules directory
                shutil.copytree(extracted_root, target)
                logger.info("[INSTALL] Installed module %s to %s", module_id, target)
                return InstallResult(
                    success=True, module_id=module_id, message=f"{module_id} installed"
                )

        except zipfile.BadZipFile:
            return InstallResult(
                success=False, module_id=module_slug, message="Invalid ZIP"
            )
        except Exception as e:
            logger.warning("[INSTALL] Error installing %s: %s", module_slug, e)
            return InstallResult(
                success=False, module_id=module_slug, message=str(e)
            )
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    @classmethod
    def install_block_modules(cls, block_slugs, hub_config):
        """Install required modules for all selected functional blocks.

        Fetches each block's module list from Cloud API and downloads the
        required modules that aren't already installed.

        Args:
            block_slugs: List of functional block slugs
            hub_config: HubConfig instance

        Returns:
            BulkInstallResult with counts and per-module results
        """
        cloud_url = cls.get_cloud_url()
        hub_token = cls.get_hub_token(hub_config)
        modules_dir = Path(settings.MODULES_DIR)

        # Get already-installed module IDs
        installed_ids = set()
        if modules_dir.exists():
            for d in modules_dir.iterdir():
                if d.is_dir() and not d.name.startswith('.'):
                    installed_ids.add(d.name.lstrip('_'))

        logger.info(
            "[INSTALL] Starting: blocks=%s, cloud=%s, token=%s, installed=%d",
            block_slugs, cloud_url,
            'set' if hub_token else 'EMPTY',
            len(installed_ids),
        )

        total_installed = 0
        errors = []
        results = []

        for slug in block_slugs:
            try:
                solution_url = f"{cloud_url}/api/marketplace/solutions/{slug}/"
                logger.info("[INSTALL] Fetching solution: %s", solution_url)
                resp = http_requests.get(solution_url, timeout=15)

                if resp.status_code != 200:
                    msg = f"Solution {slug}: HTTP {resp.status_code}"
                    logger.warning("[INSTALL] %s", msg)
                    errors.append(msg)
                    continue

                solution = resp.json()
                all_modules = solution.get('modules', [])

                modules_to_install = [
                    m for m in all_modules
                    if m.get('slug', '') not in installed_ids
                    and m.get('module_id', '') not in installed_ids
                    and not m.get('is_coming_soon', False)
                ]
                logger.info(
                    "[INSTALL] Solution %s: %d total, %d to install",
                    slug, len(all_modules), len(modules_to_install),
                )

                for mod in modules_to_install:
                    mod_slug = mod.get('slug', '')
                    module_id = mod.get('module_id', '') or mod_slug
                    if not mod_slug:
                        continue

                    # Skip if already installed
                    if module_id in installed_ids or mod_slug in installed_ids:
                        logger.info("[INSTALL] Skipping %s (already installed)", module_id)
                        continue

                    download_url = (
                        f"{cloud_url}/api/marketplace/modules/{mod_slug}/download/"
                    )
                    result = cls.download_and_install(mod_slug, download_url, hub_token)
                    results.append(result)

                    if result.success:
                        total_installed += 1
                        installed_ids.add(result.module_id)
                        installed_ids.add(mod_slug)
                    else:
                        errors.append(
                            f"{mod.get('name', mod_slug)}: {result.message}"
                        )
                        logger.warning(
                            "[INSTALL] Failed %s: %s", mod_slug, result.message
                        )

            except Exception as e:
                logger.warning(
                    "[INSTALL] Error processing block %s: %s", slug, e, exc_info=True
                )
                errors.append(f"Block {slug}: {e}")

        logger.info(
            "[INSTALL] Complete: %d installed, %d errors", total_installed, len(errors)
        )
        return BulkInstallResult(
            installed=total_installed, errors=errors, results=results
        )

    @classmethod
    def run_post_install(cls, *, load_all=False, load_single=None,
                         run_migrations=True, sync_permissions=False,
                         hub_id=None, schedule_restart=False):
        """Run post-installation steps.

        Args:
            load_all: Load all active modules (for batch installs)
            load_single: Load a single module by ID
            run_migrations: Run Django migrations
            sync_permissions: Sync module permissions to database
            hub_id: Hub ID (required if sync_permissions=True)
            schedule_restart: Schedule server restart after install
        """
        from apps.modules_runtime.loader import module_loader

        # Load modules
        if load_all:
            try:
                module_loader.load_all_active_modules()
            except Exception as e:
                logger.warning("[POST-INSTALL] load_all error: %s", e)
        elif load_single:
            try:
                module_loader.load_module(load_single)
            except Exception as e:
                logger.warning("[POST-INSTALL] load_module(%s) error: %s", load_single, e)

        # Run migrations
        if run_migrations:
            try:
                from django.core.management import call_command
                call_command('migrate', '--run-syncdb')
            except Exception as e:
                logger.warning("[POST-INSTALL] Migration error (non-fatal): %s", e)

        # Sync permissions
        if sync_permissions and hub_id:
            try:
                from apps.core.services.permission_service import PermissionService
                PermissionService.sync_all_module_permissions(hub_id)
                logger.info("[POST-INSTALL] Permissions synced")
            except Exception as e:
                logger.warning("[POST-INSTALL] Permission sync error: %s", e)

        # Schedule restart
        if schedule_restart:
            from apps.core.utils import schedule_server_restart
            schedule_server_restart()

    @staticmethod
    def _get_module_id_from_extracted(extracted_root, fallback):
        """Read MODULE_ID from module.py in the extracted directory.

        Falls back to the provided slug if module.py doesn't exist or
        doesn't contain MODULE_ID.
        """
        module_py = extracted_root / 'module.py'
        if module_py.exists():
            try:
                for line in module_py.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if line.startswith('MODULE_ID'):
                        value = line.split('=', 1)[1].strip().strip("'\"")
                        if value:
                            return value
            except Exception:
                pass
        return fallback
