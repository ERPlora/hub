# apps/plugins_runtime/discovery.py
from pathlib import Path
from typing import List, Dict
from importlib import import_module
from django.conf import settings
from django.apps import apps as django_apps

def discover_plugins_from_fs() -> List[Dict]:
    """
    Escanea PLUGINS_ROOT y devuelve metadatos mínimos
    para cada plugin encontrado.
    """
    root: Path = Path(settings.PLUGINS_ROOT)
    found = []

    if not root.exists():
        return found

    for d in root.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith(".") or d.name.startswith("_"):
            continue
        if not (d / "__init__.py").exists():
            continue

        plugin_id = d.name

        # plugin.json opcional
        meta = {
            "plugin_id": plugin_id,
            "install_path": str(d),
            "name": plugin_id.title(),
            "description": "",
            "version": "1.0.0",
            "author": "",
            "menu": {
                "label": plugin_id.title(),
                "icon": "cube-outline",
                "order": 100,
                "show": True,
            },
            "main_url": f"/plugins/{plugin_id}/",
        }

        json_path = d / "plugin.json"
        if json_path.exists():
            import json
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    file_meta = json.load(f)
                meta.update(file_meta)
                meta["install_path"] = str(d)

                # Si el plugin.json tiene menu.url, usarlo como main_url
                if "menu" in file_meta and "url" in file_meta["menu"]:
                    meta["main_url"] = file_meta["menu"]["url"]
            except Exception as e:
                print(f"[PLUGINS][DISCOVER] Error leyendo {json_path}: {e}")

        found.append(meta)

    return found


def sync_fs_with_db(dev_mode: bool = False):
    """
    Sincroniza lo que hay en el filesystem con la BD Plugin.
    En dev_mode: crea los plugins que no existen y los marca activos por defecto.
    """
    Plugin = django_apps.get_model("plugins_admin", "Plugin")
    discovered = discover_plugins_from_fs()

    for md in discovered:
        plugin_id = md["plugin_id"]

        plugin, created = Plugin.objects.get_or_create(
            plugin_id=plugin_id,
            defaults={
                "name": md.get("name", plugin_id),
                "description": md.get("description", ""),
                "version": md.get("version", "1.0.0"),
                "author": md.get("author", ""),
                "icon": md.get("icon", "cube-outline"),
                "category": md.get("category", "general"),
                "install_path": md.get("install_path", ""),
                "is_installed": True,
                "is_active": True if dev_mode else False,
                "menu_label": md.get("menu", {}).get("label", md.get("name", plugin_id)),
                "menu_icon": md.get("menu", {}).get("icon", md.get("icon", "cube-outline")),
                "menu_order": md.get("menu", {}).get("order", 100),
                "show_in_menu": md.get("menu", {}).get("show", True),
                "main_url": md.get("main_url", ""),
            },
        )

        if not created:
            # actualizar campos básicos
            plugin.name = md.get("name", plugin.name)
            plugin.description = md.get("description", plugin.description)
            plugin.version = md.get("version", plugin.version)
            plugin.author = md.get("author", plugin.author)
            plugin.icon = md.get("icon", plugin.icon)
            plugin.category = md.get("category", plugin.category)
            plugin.install_path = md.get("install_path", plugin.install_path)
            plugin.menu_label = md.get("menu", {}).get("label", plugin.menu_label or plugin.name)
            plugin.menu_icon = md.get("menu", {}).get("icon", plugin.menu_icon or plugin.icon)
            plugin.menu_order = md.get("menu", {}).get("order", plugin.menu_order)
            plugin.show_in_menu = md.get("menu", {}).get("show", plugin.show_in_menu)
            plugin.main_url = md.get("main_url", plugin.main_url)
            plugin.is_installed = True
            plugin.save()
