"""
Dynamic Plugin Middleware Manager

This middleware dynamically loads and executes middlewares from active plugins.
It checks the database on each request to determine which plugins are active,
and only runs middlewares for those plugins.

This solves the problem of plugins being deactivated but their middleware still running.
"""

import json
from pathlib import Path
from django.conf import settings
from django.utils.module_loading import import_string


class PluginMiddlewareManager:
    """
    Dynamically manages plugin middlewares based on plugin active status.

    Flow:
    1. On each request, check which plugins are active in DB
    2. For each active plugin, check if it has middleware defined in plugin.json
    3. Execute those middlewares in order
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._middleware_cache = {}  # Cache middleware instances
        self._plugin_middleware_map = {}  # Map plugin_id → middleware path

        # Build initial map of plugin → middleware from filesystem
        self._load_plugin_middleware_map()

    def _load_plugin_middleware_map(self):
        """
        Scan all plugin directories and build a map of plugin_id → middleware_path.
        This is done once at startup to avoid filesystem I/O on every request.
        """
        plugins_dir = getattr(settings, 'PLUGINS_DIR', None)
        if not plugins_dir or not Path(plugins_dir).exists():
            return

        for plugin_dir in Path(plugins_dir).iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip disabled plugins (start with _ or .)
            if plugin_dir.name.startswith('.') or plugin_dir.name.startswith('_'):
                continue

            # Check for middleware in plugin.json
            plugin_json_path = plugin_dir / 'plugin.json'
            if not plugin_json_path.exists():
                continue

            try:
                with open(plugin_json_path, 'r') as f:
                    plugin_metadata = json.load(f)

                # Store middleware path if defined
                if 'middleware' in plugin_metadata:
                    middleware_class = plugin_metadata['middleware']
                    middleware_path = f"{plugin_dir.name}.{middleware_class}"
                    self._plugin_middleware_map[plugin_dir.name] = middleware_path
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[PLUGIN_MIDDLEWARE_MANAGER] Warning: Could not load middleware from {plugin_dir.name}/plugin.json: {e}")

    def _get_active_plugin_ids(self):
        """
        Get list of active plugin IDs from filesystem.
        Only returns plugins that are NOT prefixed with _ or .

        This uses the filesystem as the source of truth for plugin activation.
        To deactivate a plugin, simply rename its directory to start with _ or .
        Example: cash_register → _cash_register (disabled)
        """
        plugins_dir = getattr(settings, 'PLUGINS_DIR', None)
        if not plugins_dir or not Path(plugins_dir).exists():
            return []

        active_plugins = []
        for plugin_dir in Path(plugins_dir).iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip disabled plugins (start with _ or .)
            if plugin_dir.name.startswith('.') or plugin_dir.name.startswith('_'):
                continue

            active_plugins.append(plugin_dir.name)

        return active_plugins

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
                print(f"[PLUGIN_MIDDLEWARE_MANAGER] Error loading middleware {middleware_path}: {e}")
                return None

        return self._middleware_cache[middleware_path]

    def __call__(self, request):
        """
        Process request through active plugin middlewares.
        """
        # Get list of currently active plugins
        active_plugin_ids = self._get_active_plugin_ids()

        # Collect middleware instances for active plugins
        active_middlewares = []
        for plugin_id in active_plugin_ids:
            if plugin_id in self._plugin_middleware_map:
                middleware_path = self._plugin_middleware_map[plugin_id]
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
