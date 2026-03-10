"""
Module Setup Redirect Middleware

Redirects users to the module's setup page when:
- The module has SETUP.required = True
- The setup check function returns False (setup incomplete)
- The user is not already on the setup URL
"""
import importlib
import logging
import re

from django.shortcuts import redirect

logger = logging.getLogger(__name__)

# Match /m/{module_id}/ but NOT /m/{module_id}/setup/
MODULE_URL_RE = re.compile(r'^/m/(?P<module_id>[a-z_]+)/')
SETUP_URL_RE = re.compile(r'^/m/[a-z_]+/setup/')

class ModuleSetupRedirectMiddleware:
    """Redirect to setup page for modules with required but incomplete setup."""

    def __init__(self, get_response):
        self.get_response = get_response
        # Build a set of module IDs that have required setup at startup
        self._required_modules = self._discover_required_modules()

    def _discover_required_modules(self):
        """Find modules with SETUP.required=True at startup."""
        from django.conf import settings
        from pathlib import Path

        required = {}
        modules_dir = Path(settings.MODULES_DIR)
        if not modules_dir.exists():
            return required

        for module_path in modules_dir.iterdir():
            if not module_path.is_dir() or module_path.name.startswith(('_', '.')):
                continue
            module_id = module_path.name
            try:
                mod = importlib.import_module(f'{module_id}.module')
                setup = getattr(mod, 'SETUP', None)
                if setup and setup.get('required'):
                    required[module_id] = setup.get('check', '')
            except (ImportError, ModuleNotFoundError):
                continue
        return required

    def __call__(self, request):
        path = request.path

        # Only check module URLs, skip setup URLs, API, and non-module paths
        if not MODULE_URL_RE.match(path) or SETUP_URL_RE.match(path):
            return self.get_response(request)

        # Skip API requests and HTMX partial requests (only redirect full page loads)
        if path.startswith('/api/') or '/api/' in path:
            return self.get_response(request)
        if getattr(request, 'htmx', None) and request.htmx:
            return self.get_response(request)

        match = MODULE_URL_RE.match(path)
        module_id = match.group('module_id')

        # Only check modules with required setup
        check_name = self._required_modules.get(module_id)
        if not check_name:
            return self.get_response(request)

        # Run the setup check
        try:
            mod = importlib.import_module(f'{module_id}.views')
            check_fn = getattr(mod, check_name, None)
            if check_fn and callable(check_fn) and not check_fn():
                return redirect(f'/m/{module_id}/setup/')
        except Exception as e:
            logger.debug('Setup check for %s failed: %s', module_id, e)

        return self.get_response(request)
