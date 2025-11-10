# Static Files Directory

Esta carpeta contiene todos los archivos estáticos del Hub (CSS, JavaScript, imágenes, fuentes, etc.).

## Estructura

```
static/
├── css/              # Estilos CSS custom
│   ├── ionic-theme.css
│   └── custom.css
├── js/               # JavaScript custom
│   ├── alpine-components.js
│   └── utils.js
├── img/              # Imágenes y logos
│   └── logo.png
├── fonts/            # Fuentes custom (opcional)
└── ionicons/         # Iconos Ionic (descargados localmente)
```

## Uso en Templates

```html
{% load static %}

<!-- CSS -->
<link rel="stylesheet" href="{% static 'css/ionic-theme.css' %}">

<!-- JavaScript -->
<script src="{% static 'js/alpine-components.js' %}"></script>

<!-- Imágenes -->
<img src="{% static 'img/logo.png' %}" alt="CPOS Hub">

<!-- Iconicons -->
<ion-icon name="cube-outline"></ion-icon>
```

## ⚠️ Importante

- **Imágenes de la app**: guardar en `static/img/`
- **CSS custom**: guardar en `static/css/`
- **JavaScript custom**: guardar en `static/js/`
- **NO confundir con `assets/`**: `assets/` solo para iconos de la app (.icns, .ico)

## Archivos CDN vs Locales

Por defecto, Ionic y Alpine.js se cargan desde CDN en desarrollo:

```html
<!-- CDN (desarrollo) -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@ionic/core/css/ionic.bundle.css" />
```

Para producción (offline), descarga y coloca en `static/`:
- Alpine.js → `static/js/alpine.min.js`
- Ionic → `static/css/ionic.bundle.css` + `static/js/ionic.esm.js`

## Collectstatic

En producción, Django recolecta todos los archivos estáticos:

```bash
python manage.py collectstatic
```

Esto copia archivos de:
- `static/` (este directorio)
- `apps/*/static/` (static de cada app)

A: `staticfiles/` (configurado en `STATIC_ROOT`)
