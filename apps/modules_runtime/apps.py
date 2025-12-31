from django.apps import AppConfig

from config import settings


class ModulesRuntimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.modules_runtime'

    def ready(self):
        """
        Al arrancar Django:
        - Escanea /modules y carga todos los activos (sin _ al inicio)
        - Registra URLs de todos los módulos activos
        """
        from .loader import module_loader
        from .router import register_module_urls

        try:
            # 1) Cargar todos los módulos activos del filesystem
            loaded_count = module_loader.load_all_active_modules()
            print(f"[MODULES_RUNTIME] Loaded {loaded_count} active modules")

            # 2) Registrar URLs de cada módulo cargado
            for module_id, module_info in module_loader.loaded_modules.items():
                # Registrar URLs del módulo
                register_module_urls(module_id, module_id, f'/m/{module_id}/')

        except Exception as e:
            print(f"[MODULES_RUNTIME] Error loading modules: {e}")
            import traceback
            traceback.print_exc()
            return
