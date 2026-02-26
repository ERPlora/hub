from django.apps import AppConfig
from django.conf import settings
from pathlib import Path


class ModulesRuntimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.modules_runtime'

    def ready(self):
        """
        Al arrancar Django:
        - Modules already in INSTALLED_APPS (added by settings load_modules())
        - Register URL patterns for each active module
        """
        from .router import register_module_urls

        try:
            modules_dir = Path(settings.MODULES_DIR)
            if not modules_dir.exists():
                return

            registered = 0
            installed_apps = set(settings.INSTALLED_APPS)

            for module_dir in sorted(modules_dir.iterdir()):
                if not module_dir.is_dir():
                    continue
                if module_dir.name.startswith('.') or module_dir.name.startswith('_'):
                    continue

                module_id = module_dir.name
                if module_id not in installed_apps:
                    continue

                try:
                    register_module_urls(module_id, module_id, f'/m/{module_id}/')
                    registered += 1
                except Exception as e:
                    print(f"[MODULES_RUNTIME] Failed to register URLs for '{module_id}': {e}")

            print(f"[MODULES_RUNTIME] Registered URLs for {registered} modules")

        except Exception as e:
            print(f"[MODULES_RUNTIME] Error registering module URLs: {e}")
            import traceback
            traceback.print_exc()
