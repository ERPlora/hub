# apps/modules_runtime/router.py
from typing import Optional
from importlib import import_module
from django.urls import path, include

module_urlpatterns = []
module_api_urlpatterns = []


def _normalize_prefix(prefix: str) -> str:
    prefix = (prefix or "").strip()
    if not prefix:
        return ""
    prefix = prefix.strip("/")
    return prefix + "/"


def register_module_urls(module_id: str, module_name: str, main_url: Optional[str] = None):
    try:
        urls_module = import_module(f"{module_name}.urls")
    except ModuleNotFoundError:
        print(f"[MODULES][URLS] '{module_id}' no tiene urls.py, se omite")
        return

    if main_url:
        prefix = _normalize_prefix(main_url)
    else:
        prefix = _normalize_prefix(f"m/{module_id}/")

    app_name = getattr(urls_module, "app_name", module_name)

    pattern = path(prefix, include((urls_module.urlpatterns, app_name)))
    module_urlpatterns.append(pattern)

    print(f"[MODULES][URLS] Registradas URLs de '{module_id}' en '/{prefix}'")

    # Also register API URLs if the module has api.py with api_urlpatterns
    try:
        api_module = import_module(f"{module_name}.api")
        api_urls = getattr(api_module, 'api_urlpatterns', None)
        if api_urls:
            api_prefix = f"api/v1/m/{module_id}/"
            api_namespace = f"api_{module_id}"
            api_pattern = path(api_prefix, include((api_urls, api_namespace)))
            module_api_urlpatterns.append(api_pattern)
            print(f"[MODULES][API] Registradas API URLs de '{module_id}' en '/{api_prefix}'")
    except ModuleNotFoundError:
        pass  # Module doesn't have api.py — normal, skip
    except Exception as e:
        print(f"[MODULES][API] Error loading API from '{module_id}': {e}")
