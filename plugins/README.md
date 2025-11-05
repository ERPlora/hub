# CPOS Hub Plugins

This directory contains all installed plugins for the CPOS Hub.

## Plugin Structure

Each plugin should follow this structure:

```
plugins/
└── my-plugin/
    ├── plugin.json          # Plugin metadata (required)
    ├── __init__.py          # Python package init
    ├── apps.py              # Django app configuration
    ├── models.py            # Database models (optional)
    ├── views.py             # Views (optional)
    ├── urls.py              # URL routing (optional)
    ├── templates/           # Templates (optional)
    │   └── my-plugin/
    │       └── index.html
    ├── static/              # Static files (optional)
    │   └── my-plugin/
    │       ├── css/
    │       ├── js/
    │       └── img/
    └── migrations/          # Database migrations (optional)
        └── __init__.py
```

## plugin.json Format

```json
{
    "plugin_id": "my-plugin",
    "name": "My Plugin",
    "version": "1.0.0",
    "description": "A sample plugin for CPOS Hub",
    "author": "Your Name",
    "author_email": "your.email@example.com",
    "license": "MIT",
    "icon": "cube-outline",
    "category": "general",
    "menu": {
        "label": "My Plugin",
        "icon": "cube-outline",
        "order": 100,
        "show": true
    },
    "main_url": "my-plugin:index",
    "dependencies": [],
    "min_hub_version": "1.0.0"
}
```

## Plugin Lifecycle

1. **Installation**: Plugin ZIP is downloaded from Cloud and extracted here
2. **Registration**: Plugin metadata is saved to database (Plugin model)
3. **Activation**: Plugin is loaded dynamically into Django INSTALLED_APPS
4. **Migration**: Plugin migrations are applied to database
5. **Menu Integration**: Plugin menu item appears in sidebar (if show=true)

## Creating a Plugin

See the example plugin in `plugins/_example-plugin/` for a template.

## Plugin API

Plugins can access Hub core functionality through:
- `apps.core.models`: HubConfig, LocalUser, StoreConfig
- `apps.core.utils`: Helper functions
- Django ORM for database access
- Django templates and static files

## Plugin Development

During development, you can manually place a plugin in this directory and it will be auto-detected on Hub restart.
