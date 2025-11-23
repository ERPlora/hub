# Plugin Template

Este directorio contiene archivos template para crear nuevos plugins.

## Uso

NO uses este directorio directamente. Usa el comando `create_plugin`:

```bash
python manage.py create_plugin mi-plugin --name "Mi Plugin" --author "Tu Nombre"
```

Este comando:
1. Crea un nuevo directorio `plugins/mi-plugin/`
2. Copia y adapta los templates necesarios
3. Genera estructura completa del plugin
4. Configura archivos base (models, views, urls, templates)

## Estructura Generada

El comando `create_plugin` genera automáticamente:

```
mi-plugin/
├── plugin.json              # Metadata
├── __init__.py              # Package init
├── apps.py                  # Django app config
├── models.py                # Modelos
├── views.py                 # Vistas
├── urls.py                  # URLs
├── templates/
│   └── mi-plugin/
│       └── index.html
├── static/
│   └── mi-plugin/
│       ├── css/
│       ├── js/
│       └── img/
├── migrations/
│   └── __init__.py
├── management/
│   └── commands/
├── tests/
│   ├── __init__.py
│   └── test_basic.py
├── README.md
├── LICENSE
└── .gitignore
```

## Documentación Completa

Ver [plugins/README.md](../README.md) para guía completa de desarrollo de plugins.
