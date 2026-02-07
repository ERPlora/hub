# Static Files Directory

Esta carpeta contiene todos los archivos estaticos del Hub (CSS, JavaScript, imagenes, fuentes, etc.).

## Estructura

```
static/
├── css/
│   ├── main.css                # Estilos hub (fonts, HTMX, Alpine.js, variables hub)
│   └── themes/
│       ├── default/
│       │   ├── theme.css       # Colores del tema default (indigo)
│       │   └── erplorer-logo.svg
│       └── blue/
│           ├── theme.css       # Colores del tema blue (sky)
│           └── erplorer-logo.svg
├── fonts/
│   └── plus-jakarta-sans/      # Plus Jakarta Sans (local)
├── js/                         # JavaScript custom
├── img/                        # Imagenes y logos
└── icons/                      # Iconos
```

## CSS Loading Order (base.html)

```html
{% load static %}

<!-- 1. @erplora/ux CSS (design system) -->
<link rel="stylesheet" href="{% static 'ux/ux.min.css' %}">

<!-- 2. Bootstrap Grid -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap-grid.min.css">

<!-- 3. Color Theme (overrides --ux-* variables) -->
<link rel="stylesheet" href="{% static 'css/themes/' %}{{ HUB_CONFIG.color_theme }}/theme.css">

<!-- 4. Hub custom styles (fonts + HTMX/Alpine helpers) -->
<link rel="stylesheet" href="{% static 'css/main.css' %}">
```

## Theming

Los temas solo sobreescriben las CSS custom properties de `@erplora/ux` (`--ux-primary`, `--ux-danger`, etc.).

Dark mode se aplica con la clase `ux-dark` en `<html>` y `dark` en `<body>`.

## Collectstatic

```bash
python manage.py collectstatic
```
