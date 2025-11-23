from django.apps import AppConfig

from config import settings

class PluginsRuntimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.plugins_runtime'

    def ready(self):
        """
        Al arrancar Django:
        - Escanea /plugins y carga todos los activos (sin _ al inicio)
        - Registra URLs de todos los plugins activos
        """
        from .loader import plugin_loader
        from .router import register_plugin_urls

        try:
            # 1) Cargar todos los plugins activos del filesystem
            loaded_count = plugin_loader.load_all_active_plugins()
            print(f"[PLUGINS_RUNTIME] Loaded {loaded_count} active plugins")

            # 2) Registrar URLs de cada plugin cargado
            for plugin_id, plugin_info in plugin_loader.loaded_plugins.items():
                # Registrar URLs del plugin
                register_plugin_urls(plugin_id, plugin_id, f'/plugins/{plugin_id}/')

        except Exception as e:
            print(f"[PLUGINS_RUNTIME] Error loading plugins: {e}")
            import traceback
            traceback.print_exc()
            return 