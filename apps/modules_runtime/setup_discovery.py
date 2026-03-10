"""
Module Setup Discovery

Scans installed modules for SETUP descriptors and checks which ones
still need initial configuration.
"""
import importlib
import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def get_pending_module_setups():
    """
    Scan installed modules for pending setup (SETUP descriptor with unmet check).
    Returns list of dicts: {module_id, title, description, icon, url}
    """
    modules_dir = Path(settings.MODULES_DIR)
    if not modules_dir.exists():
        return []

    results = []
    for module_path in sorted(modules_dir.iterdir()):
        if not module_path.is_dir() or module_path.name.startswith(('_', '.')):
            continue

        module_id = module_path.name
        try:
            mod = importlib.import_module(f'{module_id}.module')
        except (ImportError, ModuleNotFoundError):
            continue

        setup = getattr(mod, 'SETUP', None)
        if not setup:
            continue

        # Check if setup is complete
        check_name = setup.get('check')
        if check_name:
            is_complete = _run_check(module_id, check_name)
            if is_complete:
                continue

        results.append({
            'module_id': module_id,
            'title': str(setup.get('title', module_id.replace('_', ' ').title())),
            'description': str(setup.get('description', '')),
            'icon': setup.get('icon', 'settings-outline'),
            'url': f'/m/{module_id}/setup/',
        })

    return results


def _run_check(module_id, check_name):
    """Run a module's setup completion check function."""
    try:
        mod = importlib.import_module(f'{module_id}.views')
        check_fn = getattr(mod, check_name, None)
        if check_fn and callable(check_fn):
            return check_fn()
    except Exception as e:
        logger.debug('Setup check %s.%s failed: %s', module_id, check_name, e)
    return False
