# apps/modules_runtime/router.py
from typing import Optional
from importlib import import_module
from django.urls import path, include

module_urlpatterns = []


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
        prefix = _normalize_prefix(f"modules/{module_id}/")

    app_name = getattr(urls_module, "app_name", module_name)

    pattern = path(prefix, include((urls_module.urlpatterns, app_name)))
    module_urlpatterns.append(pattern)

    print(f"[MODULES][URLS] Registradas URLs de '{module_id}' en '/{prefix}'")
