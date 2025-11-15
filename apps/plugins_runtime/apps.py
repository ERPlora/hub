from django.apps import AppConfig

from config import settings
from django.db.utils import OperationalError, ProgrammingError

class PluginsRuntimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.plugins_runtime'
    
    def ready(self):
        """
        Al arrancar Django:
        - En dev: escanea /plugins, crea/actualiza Plugin en BD, marca activos.
        - Carga URLs de todos los plugins activos.
        """
        from .discovery import sync_fs_with_db
        from .router import register_plugin_urls
        from django.apps import apps as django_apps

        dev_mode = getattr(settings, "USE_LOCAL_PLUGINS_DIR", False)

        try:
            # 1) Sincronizar filesystem con BD
            sync_fs_with_db(dev_mode=dev_mode)

            # 2) Agregar plugins activos a INSTALLED_APPS y registrar URLs
            Plugin = django_apps.get_model("plugins_admin", "Plugin")
            active_plugins = Plugin.objects.filter(is_installed=True, is_active=True)

            for plugin in active_plugins:
                module_name = plugin.plugin_id  # carpeta en /plugins
                # Registrar URLs del plugin
                register_plugin_urls(plugin.plugin_id, module_name, plugin.main_url)
        except (OperationalError, ProgrammingError) as e:
            # La tabla todavía no existe (primer migrate)
            print("[PLUGINS_RUNTIME] Saltando carga de plugins: tablas aún no creadas")
            print(f"[PLUGINS_RUNTIME] Detalle: {e}")
            # No relanzamos la excepción para que 'migrate' pueda crear las tablas
            return 