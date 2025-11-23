# apps/plugins_runtime/router.py
from typing import Optional
from importlib import import_module
from django.urls import path, include

plugin_urlpatterns = []


def _normalize_prefix(prefix: str) -> str:
    prefix = (prefix or "").strip()
    if not prefix:
        return ""
    prefix = prefix.strip("/")
    return prefix + "/"


def register_plugin_urls(plugin_id: str, module_name: str, main_url: Optional[str] = None):
    try:
        urls_module = import_module(f"{module_name}.urls")
    except ModuleNotFoundError:
        print(f"[PLUGINS][URLS] '{plugin_id}' no tiene urls.py, se omite")
        return

    if main_url:
        prefix = _normalize_prefix(main_url)
    else:
        prefix = _normalize_prefix(f"plugins/{plugin_id}/")

    app_name = getattr(urls_module, "app_name", module_name)

    pattern = path(prefix, include((urls_module.urlpatterns, app_name)))
    plugin_urlpatterns.append(pattern)

    print(f"[PLUGINS][URLS] Registradas URLs de '{plugin_id}' en '/{prefix}'")
