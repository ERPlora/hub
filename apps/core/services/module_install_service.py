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
    def bulk_download_and_install(cls, modules_to_install, hub_token='', max_workers=4):
        """Download and install multiple modules in parallel.

        Thread-safe: each download_and_install() uses isolated temp files.

        Args:
            modules_to_install: List of dicts with 'slug', 'download_url', and
                optionally 'name' keys
            hub_token: Hub JWT token for authentication
            max_workers: Max concurrent downloads (default 4)

        Returns:
            BulkInstallResult with counts and per-module results
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not modules_to_install:
            return BulkInstallResult(installed=0)

        logger.info(
            "[INSTALL] Bulk downloading %d modules (max_workers=%d)",
            len(modules_to_install), max_workers,
        )

        results = []
        installed = 0
        errors = []

        def _install_one(mod_info):
            return cls.download_and_install(
                mod_info['slug'], mod_info['download_url'], hub_token
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_mod = {
                executor.submit(_install_one, mod): mod
                for mod in modules_to_install
            }
            for future in as_completed(future_to_mod):
                mod = future_to_mod[future]
                try:
                    result = future.result()
                    results.append(result)
                    if result.success and 'already installed' not in result.message:
                        installed += 1
                    elif not result.success:
                        errors.append(f"{mod.get('name', mod['slug'])}: {result.message}")
                except Exception as e:
                    logger.warning("[INSTALL] Thread error for %s: %s", mod['slug'], e)
                    errors.append(f"{mod.get('name', mod['slug'])}: {e}")

        logger.info("[INSTALL] Bulk complete: %d installed, %d errors", installed, len(errors))
        return BulkInstallResult(installed=installed, errors=errors, results=results)

    @classmethod
    def _resolve_dependencies(cls, module_slugs, installed_ids, cloud_url, hub_token=''):
        """Resolve transitive dependencies for a set of modules.

        Fetches dependency_ids from Cloud API for each module and recursively
        includes any uninstalled dependencies.

        Args:
            module_slugs: Set of module slugs to resolve dependencies for
            installed_ids: Set of already-installed module IDs
            cloud_url: Cloud API base URL
            hub_token: Hub JWT token for authentication

        Returns:
            List of dicts with 'slug', 'name', 'download_url' for dependency
            modules that are not already in module_slugs or installed_ids
        """
        headers = {}
        if hub_token:
            headers['X-Hub-Token'] = hub_token
        headers['Accept'] = 'application/json'

        # Cache of module_slug -> dependency_ids to avoid duplicate API calls
        dep_cache = {}
        extra_modules = []
        extra_slugs = set()

        # Modules we still need to check dependencies for
        to_check = set(module_slugs)
        checked = set()

        while to_check:
            slug = to_check.pop()
            if slug in checked:
                continue
            checked.add(slug)

            if slug in dep_cache:
                dep_ids = dep_cache[slug]
            else:
                try:
                    resp = http_requests.get(
                        f"{cloud_url}/api/marketplace/modules/?slug={slug}",
                        headers=headers, timeout=15,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get('results', data) if isinstance(data, dict) else data
                        if isinstance(results, list) and results:
                            dep_ids = results[0].get('dependency_ids', [])
                        else:
                            dep_ids = []
                    else:
                        dep_ids = []
                except Exception as e:
                    logger.warning("[INSTALL] Could not fetch deps for %s: %s", slug, e)
                    dep_ids = []
                dep_cache[slug] = dep_ids

            for dep_id in dep_ids:
                # dep_id is a module_id (e.g. 'sales', 'customers')
                if dep_id in installed_ids:
                    continue
                if dep_id in module_slugs or dep_id in extra_slugs:
                    # Already in install list, but check its deps too
                    to_check.add(dep_id)
                    continue
                # New dependency — add to install list
                extra_slugs.add(dep_id)
                extra_modules.append({
                    'slug': dep_id,
                    'name': dep_id,
                    'download_url': f"{cloud_url}/api/marketplace/modules/{dep_id}/download/",
                })
                # Check this dependency's deps too (transitive)
                to_check.add(dep_id)
                logger.info("[INSTALL] Resolved dependency: %s (required by %s)", dep_id, slug)

        return extra_modules

    @classmethod
    def install_block_modules(cls, block_slugs, hub_config):
        """Install required modules for all selected functional blocks.

        Phase 1: Collect all modules to install from all blocks.
        Phase 2: Resolve transitive dependencies.
        Phase 3: Download them in parallel via bulk_download_and_install().

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

        # Phase 1: Collect all modules to install from all blocks
        modules_to_install = []
        seen_slugs = set()
        errors = []

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
                for mod in solution.get('modules', []):
                    if mod.get('role') != 'required' or mod.get('is_coming_soon'):
                        continue
                    mod_slug = mod.get('slug', '')
                    module_id = mod.get('module_id', '') or mod_slug
                    if not mod_slug or mod_slug in seen_slugs:
                        continue
                    if module_id in installed_ids or mod_slug in installed_ids:
                        continue
                    seen_slugs.add(mod_slug)
                    modules_to_install.append({
                        'slug': mod_slug,
                        'name': mod.get('name', mod_slug),
                        'download_url': f"{cloud_url}/api/marketplace/modules/{mod_slug}/download/",
                    })

            except Exception as e:
                logger.warning(
                    "[INSTALL] Error processing block %s: %s", slug, e, exc_info=True
                )
                errors.append(f"Block {slug}: {e}")

        logger.info(
            "[INSTALL] Collected %d modules to install from %d blocks",
            len(modules_to_install), len(block_slugs),
        )

        # Phase 2: Resolve transitive dependencies
        if modules_to_install:
            all_slugs = {m['slug'] for m in modules_to_install}
            dep_modules = cls._resolve_dependencies(
                all_slugs, installed_ids, cloud_url, hub_token
            )
            if dep_modules:
                logger.info(
                    "[INSTALL] Adding %d dependency modules: %s",
                    len(dep_modules), [m['slug'] for m in dep_modules],
                )
                modules_to_install.extend(dep_modules)

        # Phase 3: Download all modules in parallel
        if modules_to_install:
            bulk_result = cls.bulk_download_and_install(
                modules_to_install, hub_token, max_workers=4
            )
            return BulkInstallResult(
                installed=bulk_result.installed,
                errors=errors + bulk_result.errors,
                results=bulk_result.results,
            )

        return BulkInstallResult(installed=0, errors=errors, results=[])

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
        import subprocess
        import sys
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

        # Run migrations via subprocess so the new process sees the new modules
        # in INSTALLED_APPS (the current process already loaded settings at startup)
        migrations_ok = True
        if run_migrations:
            manage_py = str(Path(settings.BASE_DIR) / 'manage.py')
            try:
                subprocess.check_call(
                    [sys.executable, manage_py, 'makemigrations', '--no-input'],
                    cwd=str(settings.BASE_DIR),
                    timeout=120,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.warning("[POST-INSTALL] makemigrations error: %s", e)
                # makemigrations failure is not critical — modules may ship their own

            try:
                subprocess.check_call(
                    [sys.executable, manage_py, 'migrate', '--run-syncdb', '--no-input'],
                    cwd=str(settings.BASE_DIR),
                    timeout=120,
                )
                logger.info("[POST-INSTALL] Migrations applied via subprocess")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.error("[POST-INSTALL] migrate FAILED: %s", e)
                migrations_ok = False
            except Exception as e:
                logger.error("[POST-INSTALL] migrate FAILED: %s", e)
                migrations_ok = False

        # Sync permissions
        if sync_permissions and hub_id:
            try:
                from apps.core.services.permission_service import PermissionService
                PermissionService.sync_all_module_permissions(hub_id)
                logger.info("[POST-INSTALL] Permissions synced")
            except Exception as e:
                logger.warning("[POST-INSTALL] Permission sync error: %s", e)

        # Schedule restart — only if migrations succeeded
        if schedule_restart:
            if not migrations_ok:
                logger.error(
                    "[POST-INSTALL] Skipping restart because migrations failed. "
                    "Fix the migration errors and restart manually."
                )
            else:
                from apps.core.utils import schedule_server_restart
                schedule_server_restart()

    @staticmethod
    def _get_module_id_from_extracted(extracted_root, fallback):
        """Read MODULE_ID from module.py in the extracted directory.

        Falls back to the provided slug (with hyphens converted to underscores)
        if module.py doesn't exist or doesn't contain MODULE_ID.
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
        # Slugs use hyphens, Python identifiers use underscores
        return fallback.replace('-', '_')
