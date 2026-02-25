"""
Dynamic Module Middleware Manager

This middleware dynamically loads and executes middlewares from active modules.
It checks the filesystem on each request to determine which modules are active,
and only runs middlewares for those modules.

This solves the problem of modules being deactivated but their middleware still running.
"""

from pathlib import Path
from django.conf import settings
from django.utils.module_loading import import_string


class ModuleMiddlewareManager:
    """
    Dynamically manages module middlewares based on module active status.

    Flow:
    1. On each request, check which modules are active in filesystem
    2. For each active module, check if it has middleware defined in module.py
    3. Execute those middlewares in order
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._middleware_cache = {}  # Cache middleware instances
        self._module_middleware_map = {}  # Map module_id → middleware path

        # Build initial map of module → middleware from filesystem
        self._load_module_middleware_map()

    def _load_module_middleware_map(self):
        """
        Scan all module directories and build a map of module_id → middleware_path.
        This is done once at startup to avoid filesystem I/O on every request.
        """
        modules_dir = getattr(settings, 'MODULES_DIR', None)
        if not modules_dir or not Path(modules_dir).exists():
            return

        for module_dir in Path(modules_dir).iterdir():
            if not module_dir.is_dir():
                continue

            # Skip disabled modules (start with _ or .)
            if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
                continue

            # Check for middleware in module.py
            module_py_path = module_dir / 'module.py'
            if not module_py_path.exists():
                continue

            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(f"{module_dir.name}.module", module_py_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)

                # Store middleware path if defined
                middleware_class = getattr(mod, 'MIDDLEWARE', None)
                if middleware_class:
                    middleware_path = f"{module_dir.name}.{middleware_class}"
                    self._module_middleware_map[module_dir.name] = middleware_path
            except Exception as e:
                print(f"[MODULE_MIDDLEWARE_MANAGER] Warning: Could not load middleware from {module_dir.name}/module.py: {e}")

    def _get_active_module_ids(self):
        """
        Get list of active module IDs from filesystem.
        Only returns modules that are NOT prefixed with _ or .

        This uses the filesystem as the source of truth for module activation.
        To deactivate a module, simply rename its directory to start with _ or .
        Example: cash_register → _cash_register (disabled)
        """
        modules_dir = getattr(settings, 'MODULES_DIR', None)
        if not modules_dir or not Path(modules_dir).exists():
            return []

        active_modules = []
        for module_dir in Path(modules_dir).iterdir():
            if not module_dir.is_dir():
                continue

            # Skip disabled modules (start with _ or .)
            if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
                continue

            active_modules.append(module_dir.name)

        return active_modules

    def _get_middleware_instance(self, middleware_path):
        """
        Get or create middleware instance.
        Caches instances to avoid repeated imports.
        """
        if middleware_path not in self._middleware_cache:
            try:
                middleware_class = import_string(middleware_path)
                self._middleware_cache[middleware_path] = middleware_class(self.get_response)
            except (ImportError, AttributeError) as e:
                print(f"[MODULE_MIDDLEWARE_MANAGER] Error loading middleware {middleware_path}: {e}")
                return None

        return self._middleware_cache[middleware_path]

    def __call__(self, request):
        """
        Process request through active module middlewares.
        """
        # Get list of currently active modules
        active_module_ids = self._get_active_module_ids()

        # Collect middleware instances for active modules
        active_middlewares = []
        for module_id in active_module_ids:
            if module_id in self._module_middleware_map:
                middleware_path = self._module_middleware_map[module_id]
                middleware_instance = self._get_middleware_instance(middleware_path)
                if middleware_instance:
                    active_middlewares.append(middleware_instance)

        # Process request through active middlewares
        response = None
        for middleware in active_middlewares:
            # Call process_request if it exists
            if hasattr(middleware, 'process_request'):
                result = middleware.process_request(request)
                if result is not None:
                    # Middleware returned a response, short-circuit
                    return result

        # Get response from next middleware/view
        response = self.get_response(request)

        # Process response through active middlewares (in reverse order)
        for middleware in reversed(active_middlewares):
            if hasattr(middleware, 'process_response'):
                response = middleware.process_response(request, response)

        return response
