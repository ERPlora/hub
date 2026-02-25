"""
Setup Wizard Views

Multi-step HTMX wizard for initial Hub configuration.
Each step saves to DB on "Next" and loads the next step partial.
"""
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from zoneinfo import available_timezones
import requests as http_requests
from apps.accounts.decorators import login_required
from apps.core.htmx import is_htmx_request
from apps.core.services.permission_service import PermissionService
from apps.configuration.models import StoreConfig, HubConfig
from config.countries import get_all_countries, get_locale_map

import logging
logger = logging.getLogger(__name__)


# =============================================================================
# Timezone data
# =============================================================================

COMMON_TIMEZONES = [
    # Europe
    'Europe/Madrid', 'Europe/London', 'Europe/Paris', 'Europe/Berlin',
    'Europe/Rome', 'Europe/Amsterdam', 'Europe/Brussels', 'Europe/Lisbon',
    'Europe/Vienna', 'Europe/Warsaw', 'Europe/Prague', 'Europe/Stockholm',
    'Europe/Helsinki', 'Europe/Athens', 'Europe/Dublin', 'Europe/Zurich',
    # Americas
    'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'America/Toronto', 'America/Mexico_City', 'America/Sao_Paulo', 'America/Buenos_Aires',
    'America/Bogota', 'America/Lima', 'America/Santiago',
    # Asia
    'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Singapore',
    'Asia/Dubai', 'Asia/Mumbai', 'Asia/Seoul', 'Asia/Bangkok',
    # Pacific
    'Australia/Sydney', 'Australia/Melbourne', 'Pacific/Auckland',
    # UTC
    'UTC',
]


def get_sorted_timezones():
    """Get timezones sorted with common ones first, then alphabetically."""
    all_tz = sorted(available_timezones())
    common_set = set(COMMON_TIMEZONES)
    other_tz = [tz for tz in all_tz if tz not in common_set and '/' in tz]
    return COMMON_TIMEZONES + other_tz


# =============================================================================
# Step configuration
# =============================================================================

TOTAL_STEPS = 4

STEP_TEMPLATES = {
    1: 'setup/partials/step1_regional.html',
    2: 'setup/partials/step2_solution.html',
    3: 'setup/partials/step3_business.html',
    4: 'setup/partials/step4_tax.html',
}

STEP_LABELS = [_('Region'), _('Modules'), _('Business'), _('Tax')]


# =============================================================================
# Context helpers
# =============================================================================

def _get_completed_steps(hub_config, store_config):
    """Determine which steps are completed based on DB state.

    Steps: 1=Regional, 2=Solution, 3=Business, 4=Tax
    Step 1 is only marked complete when step 3 has user data,
    because HubConfig always has default language/timezone values.
    """
    completed = set()
    has_solution = bool(hub_config.selected_blocks) or bool(hub_config.solution_slug)
    has_business = store_config.business_name and store_config.business_address and store_config.vat_number
    if has_business:
        completed.add(1)
        completed.add(2)
        completed.add(3)
    elif has_solution:
        completed.add(1)
        completed.add(2)
    if store_config.is_configured:
        completed.add(4)
    return completed


def _get_step_context(step, hub_config, store_config, errors=None):
    """Build context for rendering a step partial."""
    completed = _get_completed_steps(hub_config, store_config)

    # Progress width: step 1 = 0%, step 2 = 50%, step 3 = 100%
    progress_width = ((step - 1) / (TOTAL_STEPS - 1)) * 100 if TOTAL_STEPS > 1 else 0

    context = {
        'current_step': step,
        'total_steps': TOTAL_STEPS,
        'completed_steps': completed,
        'step_labels': STEP_LABELS,
        'progress_width': progress_width,
        'hub_config': hub_config,
        'store_config': store_config,
        'languages': settings.LANGUAGES,
        'errors': errors,
    }

    # Step-specific data
    if step == 1:
        timezones = get_sorted_timezones()
        countries = get_all_countries()
        locale_map = get_locale_map(settings.LANGUAGES)
        context['timezones_json'] = json.dumps(timezones)
        context['countries_json'] = json.dumps(countries, ensure_ascii=False)
        context['locale_map_json'] = json.dumps(locale_map, ensure_ascii=False)
    elif step == 2:
        solutions = _fetch_solutions()
        # Group blocks by block_type category for the template
        category_order = [
            'core', 'commerce', 'services', 'hospitality', 'hr',
            'finance', 'operations', 'marketing', 'utility', 'compliance', 'specialized',
        ]
        category_labels = {
            'core': _('Core'), 'commerce': _('Commerce'), 'services': _('Services'),
            'hospitality': _('Hospitality'), 'hr': _('HR'), 'finance': _('Finance'),
            'operations': _('Operations'), 'marketing': _('Marketing'),
            'utility': _('Utility'), 'compliance': _('Compliance'), 'specialized': _('Specialized'),
        }
        blocks_by_category = {}
        for s in solutions:
            cat = s.get('block_type', '') or 'other'
            blocks_by_category.setdefault(cat, []).append(s)
        # Build ordered list of (category_key, category_label, blocks)
        grouped_blocks = []
        for cat in category_order:
            if cat in blocks_by_category:
                grouped_blocks.append((cat, str(category_labels.get(cat, cat.title())), blocks_by_category[cat]))
        # Any remaining categories not in the order
        for cat, blocks in blocks_by_category.items():
            if cat not in category_order:
                grouped_blocks.append((cat, cat.title(), blocks))
        context['grouped_blocks'] = grouped_blocks
        context['solutions'] = solutions
        context['selected_blocks_json'] = json.dumps(hub_config.selected_blocks or [])
    elif step == 3:
        countries = get_all_countries()
        locale_map = get_locale_map(settings.LANGUAGES)
        context['countries_json'] = json.dumps(countries, ensure_ascii=False)
        context['locale_map_json'] = json.dumps(locale_map, ensure_ascii=False)

    return context


def _get_full_page_context(step, hub_config, store_config):
    """Build context for the full wizard page wrapping a step."""
    context = _get_step_context(step, hub_config, store_config)
    context['step_template'] = STEP_TEMPLATES[step]

    # Full page needs all JS data for any step the user might navigate to
    timezones = get_sorted_timezones()
    countries = get_all_countries()
    locale_map = get_locale_map(settings.LANGUAGES)

    context['timezones_json'] = json.dumps(timezones)
    context['countries_json'] = json.dumps(countries, ensure_ascii=False)
    context['locale_map_json'] = json.dumps(locale_map, ensure_ascii=False)

    return context


# =============================================================================
# Validation
# =============================================================================

def _validate_step1(data):
    """Validate step 1 (regional settings)."""
    errors = []
    language = data.get('language', '').strip()
    timezone = data.get('timezone', '').strip()

    valid_langs = {code for code, _ in settings.LANGUAGES}
    if language and language not in valid_langs:
        errors.append(_('Invalid language selection.'))

    if timezone and timezone not in available_timezones() and timezone != 'UTC':
        errors.append(_('Invalid timezone.'))

    return errors


def _validate_step2(data):
    """Validate step 2 (block selection)."""
    errors = []
    blocks_json = data.get('selected_blocks', '').strip()
    if not blocks_json:
        errors.append(_('Please select at least one block'))
        return errors
    try:
        blocks = json.loads(blocks_json)
        if not isinstance(blocks, list) or len(blocks) == 0:
            errors.append(_('Please select at least one block'))
    except json.JSONDecodeError:
        errors.append(_('Invalid selection'))
    return errors


def _validate_step3(data):
    """Validate step 3 (business information)."""
    errors = []
    if not data.get('business_name', '').strip():
        errors.append(_('Business name is required'))
    if not data.get('business_address', '').strip():
        errors.append(_('Address is required'))
    if not data.get('vat_number', '').strip():
        errors.append(_('VAT/Tax ID is required'))
    return errors


def _validate_step4(data):
    """Validate step 4 (tax configuration)."""
    errors = []
    tax_rate = data.get('tax_rate', '').strip()
    if tax_rate:
        try:
            rate = Decimal(tax_rate)
            if rate < 0 or rate > 100:
                errors.append(_('Tax rate must be between 0 and 100.'))
        except InvalidOperation:
            errors.append(_('Invalid tax rate.'))
    return errors


# =============================================================================
# Save helpers
# =============================================================================

def _save_step1(data, hub_config):
    """Save step 1 data to HubConfig."""
    hub_config.language = data.get('language', 'en').strip()
    hub_config.country_code = data.get('country', '').strip().upper()
    hub_config.timezone = data.get('timezone', 'UTC').strip()
    hub_config.save()


def _get_hub_id(hub_config):
    """Get hub_id from HubConfig or fall back to settings.HUB_ID.

    HubConfig.hub_id is set during Cloud SSO login, but during setup
    it may not be populated yet. In Cloud Hubs, settings.HUB_ID is
    always set from the environment variable. In local dev, generate
    a deterministic UUID so roles/permissions can still be created.
    """
    if hub_config.hub_id:
        return str(hub_config.hub_id)

    # Fall back to settings.HUB_ID (set in web.py from env var)
    settings_hub_id = getattr(settings, 'HUB_ID', None)
    if settings_hub_id:
        # Persist it to HubConfig so future lookups work
        hub_config.hub_id = settings_hub_id
        hub_config.save(update_fields=['hub_id'])
        logger.info(f"Set hub_id from settings.HUB_ID: {settings_hub_id}")
        return str(settings_hub_id)

    # Local development without HUB_ID — generate a deterministic one
    generated_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'erplora.local'))
    hub_config.hub_id = generated_id
    hub_config.save(update_fields=['hub_id'])
    logger.info(f"Generated local hub_id: {generated_id}")
    return generated_id


def _get_installed_module_ids():
    """Get list of installed module IDs from the modules directory."""
    modules_dir = Path(settings.MODULES_DIR)
    installed = []
    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            if module_dir.is_dir() and not module_dir.name.startswith('.'):
                installed.append(module_dir.name.lstrip('_'))
    return installed


def _get_module_id_from_zip(extracted_root, fallback):
    """Read MODULE_ID from module.py or module.json, falling back to slug."""
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
    module_json = extracted_root / 'module.json'
    if module_json.exists():
        try:
            data = json.loads(module_json.read_text(encoding='utf-8'))
            if data.get('id'):
                return data['id']
        except Exception:
            pass
    return fallback


def _install_module_from_url(module_slug, download_url, hub_token):
    """Download and install a single module from Cloud.

    Returns (success: bool, message: str).
    """
    modules_dir = Path(settings.MODULES_DIR)
    headers = {}
    if hub_token:
        headers['X-Hub-Token'] = hub_token

    try:
        resp = http_requests.get(download_url, headers=headers, timeout=120, stream=True)
        resp.raise_for_status()
    except Exception as e:
        return False, f"Download failed: {e}"

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

            items = list(tmp_extract_path.iterdir())
            extracted_root = items[0] if len(items) == 1 and items[0].is_dir() else tmp_extract_path

            module_id = _get_module_id_from_zip(extracted_root, module_slug)

            target = modules_dir / module_id
            if target.exists() or (modules_dir / f"_{module_id}").exists():
                return True, f"{module_id} already installed"

            shutil.copytree(extracted_root, target)
            logger.info(f"Installed module {module_id} to {target}")
            return True, f"{module_id} installed"

    except zipfile.BadZipFile:
        return False, "Invalid ZIP"
    except Exception as e:
        return False, str(e)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _get_dev_modules_dir():
    """Get the development modules directory (non-sandbox).

    Used as fallback when Cloud download fails — copies module source
    from the dev environment instead.
    """
    from config.paths import DataPaths
    paths = DataPaths.__new__(DataPaths)
    paths.platform = __import__('sys').platform
    paths._base_dir = None
    # Force non-sandbox base dir
    if paths.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "ERPloraHub"
    else:
        base = Path.home() / ".erplora-hub"
    modules = base / "modules"
    return modules if modules.exists() else None


def _install_module_local(module_id, dev_modules_dir, target_dir):
    """Copy a module from the dev modules directory to the target."""
    source = dev_modules_dir / module_id
    if not source.exists():
        return False, f"{module_id} not found in dev modules"
    target = target_dir / module_id
    if target.exists():
        return True, f"{module_id} already installed"
    shutil.copytree(source, target)
    logger.info(f"Copied module {module_id} from dev: {source} -> {target}")
    return True, f"{module_id} copied from dev"


def _install_block_modules(block_slugs, hub_config):
    """Install required modules for all selected blocks.

    Fetches each block's module list from Cloud API and downloads/installs
    the required modules that aren't already installed.

    Fallback: if Cloud download fails (no ZIP available), copies the module
    from the development modules directory.
    """
    cloud_url = _get_cloud_base_url()
    installed_ids = _get_installed_module_ids()
    hub_token = hub_config.hub_jwt if hasattr(hub_config, 'hub_jwt') else ''
    modules_dir = Path(settings.MODULES_DIR)
    dev_modules = _get_dev_modules_dir()

    total_installed = 0
    errors = []

    for slug in block_slugs:
        try:
            resp = http_requests.get(
                f"{cloud_url}/api/marketplace/solutions/{slug}/",
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch solution {slug}: HTTP {resp.status_code}")
                continue

            solution = resp.json()
            required_modules = [
                m for m in solution.get('modules', [])
                if m.get('role') == 'required'
                and m.get('slug', '') not in installed_ids
                and m.get('module_id', '') not in installed_ids
                and not m.get('is_coming_soon', False)
            ]

            for mod in required_modules:
                mod_slug = mod.get('slug', '')
                module_id = mod.get('module_id', '') or mod_slug
                if not mod_slug:
                    continue

                # Skip if already installed (by module_id or slug)
                if module_id in installed_ids or mod_slug in installed_ids:
                    continue

                # Try 1: Download from Cloud
                download_url = f"{cloud_url}/api/marketplace/modules/{mod_slug}/download/"
                ok, msg = _install_module_from_url(mod_slug, download_url, hub_token)

                # Try 2: Fallback to local dev copy
                if not ok and dev_modules:
                    ok, msg = _install_module_local(module_id, dev_modules, modules_dir)
                    if ok:
                        msg += " (local fallback)"

                if ok:
                    total_installed += 1
                    installed_ids.append(module_id)
                    installed_ids.append(mod_slug)
                else:
                    errors.append(f"{mod.get('name', mod_slug)}: {msg}")
                    logger.warning(f"Failed to install module {mod_slug}: {msg}")

        except Exception as e:
            logger.warning(f"Error processing block {slug}: {e}")
            errors.append(f"Block {slug}: {e}")

    if total_installed:
        logger.info(f"Installed {total_installed} modules from {len(block_slugs)} blocks")
    if errors:
        logger.warning(f"Module install errors: {errors}")

    return total_installed, errors


def _save_step2(data, hub_config):
    """Save step 2 data (block selection) to HubConfig and create roles."""
    blocks = json.loads(data.get('selected_blocks', '[]'))

    hub_config.selected_blocks = blocks
    # Retrocompat: store first block as solution_slug
    hub_config.solution_slug = blocks[0] if blocks else ''
    hub_config.solution_name = ''
    hub_config.save()

    # Fetch roles from ALL selected blocks and create them
    if blocks:
        hub_id = _get_hub_id(hub_config)
        all_roles = []
        for slug in blocks:
            roles_data = _fetch_solution_roles(slug)
            if roles_data:
                all_roles.extend(roles_data)
        if all_roles:
            PermissionService.create_solution_roles(hub_id, all_roles)
            logger.info(f"Created {len(all_roles)} roles from {len(blocks)} blocks")


def _save_step3(data, store_config):
    """Save step 3 data (business info) to StoreConfig."""
    store_config.business_name = data.get('business_name', '').strip()
    store_config.business_address = data.get('business_address', '').strip()
    store_config.vat_number = data.get('vat_number', '').strip()
    store_config.phone = data.get('phone', '').strip()
    store_config.email = data.get('email', '').strip()
    store_config.save()


def _save_step4(data, store_config):
    """Save step 4 data to StoreConfig and mark as configured."""
    tax_rate = data.get('tax_rate', '21').strip()
    try:
        store_config.tax_rate = Decimal(tax_rate) if tax_rate else Decimal('21')
    except InvalidOperation:
        store_config.tax_rate = Decimal('21')

    store_config.tax_included = data.get('tax_included') == 'on'
    store_config.is_configured = True
    store_config.save()


# =============================================================================
# Cloud API helpers
# =============================================================================

def _get_cloud_base_url():
    """Get the Cloud API base URL from settings."""
    return getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')


def _fetch_solutions():
    """Fetch available solutions from Cloud API."""
    try:
        url = f"{_get_cloud_base_url()}/api/marketplace/solutions/"
        resp = http_requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch solutions from Cloud: {e}")
    return []


def _schedule_restart():
    """Schedule a server restart so newly installed module URLs are registered.

    In Docker (Gunicorn), sends SIGHUP to PID 1 for graceful reload.
    In local dev (runserver), touches wsgi.py to trigger autoreload.
    """
    import signal
    import threading
    from config.paths import is_docker_environment

    def _restart():
        import time
        time.sleep(3)  # Let the response be sent first
        if is_docker_environment():
            try:
                os.kill(1, signal.SIGHUP)
            except Exception:
                pass
        else:
            # Local dev: touch a file to trigger runserver autoreload
            wsgi_file = Path(settings.BASE_DIR) / 'config' / 'wsgi.py'
            if wsgi_file.exists():
                wsgi_file.touch()
                logger.info("Touched wsgi.py to trigger autoreload")

    threading.Thread(target=_restart, daemon=True).start()
    logger.info("Scheduled server restart for module URL registration")


def _fetch_solution_roles(solution_slug):
    """Fetch roles for a specific solution from Cloud API."""
    try:
        url = f"{_get_cloud_base_url()}/api/marketplace/solutions/{solution_slug}/"
        resp = http_requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('roles', [])
    except Exception as e:
        logger.warning(f"Failed to fetch solution roles from Cloud: {e}")
    return []


# =============================================================================
# Views
# =============================================================================

@login_required
def wizard(request):
    """
    Setup wizard entry point.

    GET /setup/ → Full page with step 1 (or current step based on DB state).
    """
    store_config = StoreConfig.get_config()
    hub_config = HubConfig.get_config()

    if store_config.is_configured:
        return redirect('main:index')

    # Determine which step to show based on completed data
    completed = _get_completed_steps(hub_config, store_config)
    if 3 in completed:
        initial_step = 4
    elif 2 in completed:
        initial_step = 3
    elif 1 in completed:
        initial_step = 2
    else:
        initial_step = 1

    context = _get_full_page_context(initial_step, hub_config, store_config)
    return render(request, 'setup/pages/wizard.html', context)


@login_required
def wizard_step(request, step):
    """
    Handle individual wizard steps.

    GET  /setup/step/<N>/ → Step partial (HTMX) or full page (direct access)
    POST /setup/step/<N>/ → Validate, save, return next step (or redirect on final)
    """
    if step not in STEP_TEMPLATES:
        return redirect('setup:wizard')

    store_config = StoreConfig.get_config()
    hub_config = HubConfig.get_config()

    if store_config.is_configured:
        return redirect('main:index')

    if request.method == 'POST':
        return _handle_step_post(request, step, hub_config, store_config)

    # GET request
    if is_htmx_request(request):
        context = _get_step_context(step, hub_config, store_config)
        return render(request, STEP_TEMPLATES[step], context)
    else:
        # Direct browser access (refresh/bookmark) → full page
        context = _get_full_page_context(step, hub_config, store_config)
        return render(request, 'setup/pages/wizard.html', context)


def _handle_step_post(request, step, hub_config, store_config):
    """Process a step POST: validate → save → return next step or redirect."""
    data = request.POST

    # Validate
    validators = {1: _validate_step1, 2: _validate_step2, 3: _validate_step3, 4: _validate_step4}
    errors = validators[step](data)

    if errors:
        # Re-render same step with errors
        context = _get_step_context(step, hub_config, store_config, errors=errors)
        return render(request, STEP_TEMPLATES[step], context)

    # Save — steps 1 & 2 save to hub_config, steps 3 & 4 save to store_config
    savers = {1: _save_step1, 2: _save_step2, 3: _save_step3, 4: _save_step4}
    if step in (1, 2):
        savers[step](data, hub_config)
    else:
        savers[step](data, store_config)

    # Return next step or redirect
    if step < TOTAL_STEPS:
        next_step = step + 1
        # Refresh configs after save
        hub_config.refresh_from_db()
        store_config.refresh_from_db()
        context = _get_step_context(next_step, hub_config, store_config)
        return render(request, STEP_TEMPLATES[next_step], context)
    else:
        # Final step complete → save config, show progress screen for module install
        hub_id = _get_hub_id(hub_config)
        PermissionService.create_default_roles(hub_id)
        logger.info("Setup complete: created default roles")

        # Return the progress screen partial (handles module install via HTMX)
        blocks = hub_config.selected_blocks or []
        context = _get_step_context(step, hub_config, store_config)
        context['has_blocks'] = len(blocks) > 0
        return render(request, 'setup/partials/step_installing.html', context)


@login_required
def install_modules(request):
    """POST /setup/install-modules/ — Download & install modules for selected blocks.

    Called by the progress screen after Step 4.
    Returns JSON with results so the frontend can update the progress UI.
    """
    import json as json_mod
    hub_config = HubConfig.get_config()
    store_config = StoreConfig.get_config()
    blocks = hub_config.selected_blocks or []

    if not blocks:
        return HttpResponse(
            json_mod.dumps({'status': 'done', 'installed': 0, 'errors': []}),
            content_type='application/json',
        )

    hub_id = _get_hub_id(hub_config)

    # Install modules from selected blocks
    installed_count, errors = _install_block_modules(blocks, hub_config)

    # Load modules + run migrations + sync permissions
    try:
        from apps.modules_runtime.loader import module_loader
        module_loader.load_all_active_modules()
        from django.core.management import call_command
        call_command('migrate', '--run-syncdb')
    except Exception as e:
        logger.warning(f"Module loading/migration error (non-fatal): {e}")

    PermissionService.sync_all_module_permissions(hub_id)
    logger.info(f"Post-install: {installed_count} modules, permissions synced")

    # Schedule gentle restart so module URLs get registered on next page load
    if installed_count > 0:
        _schedule_restart()

    return HttpResponse(
        json_mod.dumps({
            'status': 'done',
            'installed': installed_count,
            'errors': errors,
            'requires_restart': installed_count > 0,
        }),
        content_type='application/json',
    )
