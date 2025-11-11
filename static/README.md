# Static Files Directory

Esta carpeta contiene todos los archivos estáticos del Hub (CSS, JavaScript, imágenes, fuentes, etc.).

## Estructura

```
static/
├── css/              # Estilos CSS
│   ├── themes/      # Temas de color (cada tema en su carpeta)
│   │   ├── default/
│   │   │   ├── ionic-theme.css       # Colores del tema default
│   │   │   └── erplorer-logo.svg     # Logo del tema default
│   │   └── blue/
│   │       ├── ionic-theme.css       # Colores del tema blue
│   │       └── erplorer-logo.svg     # Logo del tema blue
│   ├── style.css    # Estilos base y componentes
│   └── tailwind-ionic.css  # Utilidades Tailwind + Ionic
├── js/               # JavaScript custom
│   └── tailwind.cdn.js  # Tailwind CSS (offline)
├── img/              # Imágenes y logos generales
├── fonts/            # Fuentes custom (opcional)
└── media/            # Uploads (logos de tienda, etc.)
```

## Uso en Templates

```html
{% load static %}
{% load theme_tags %}

<!-- Ionic CSS -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@ionic/core/css/ionic.bundle.css" />

<!-- Theme CSS (carga dinámicamente desde carpeta del tema) -->
<link rel="stylesheet" href="{% theme_css hub_config.color_theme %}" id="theme-stylesheet">
<!-- O directamente: -->
<link rel="stylesheet" href="{% static 'css/themes/' %}{{ hub_config.color_theme }}/ionic-theme.css">

<!-- Base Styles -->
<link rel="stylesheet" href="{% static 'css/style.css' %}">

<!-- Tailwind CSS (offline) -->
<script src="{% static 'js/tailwind.cdn.js' %}"></script>
<link rel="stylesheet" href="{% static 'css/tailwind-ionic.css' %}">

<!-- Logo del tema actual -->
<img src="{% theme_logo hub_config.color_theme %}" alt="CPOS Hub">
<!-- O directamente: -->
<img src="{% static 'css/themes/' %}{{ hub_config.color_theme }}/erplorer-logo.svg">

<!-- Iconicons -->
<ion-icon name="cube-outline"></ion-icon>
```

## ⚠️ Importante

- **Imágenes de la app**: guardar en `static/img/`
- **CSS custom**: guardar en `static/css/`
- **JavaScript custom**: guardar en `static/js/`
- **NO confundir con `assets/`**: `assets/` solo para iconos de la app (.icns, .ico)
- **Todos los archivos son locales**: El Hub funciona 100% offline sin dependencias de CDN

## Archivos Locales (Offline-First)

Todos los recursos frontend están disponibles localmente:

```
static/
├── css/
│   ├── ionic.bundle.css         # Ionic CSS completo (38KB)
│   └── tailwind-ionic.css       # Utilidades Tailwind + Ionic
├── js/
│   ├── alpine.min.js            # Alpine.js 3.x (44KB)
│   ├── ionic/                   # Ionic Core completo (6.5MB con todos los componentes)
│   │   ├── ionic.esm.js        # Entry point ESM
│   │   └── p-*.entry.js        # 93 componentes lazy-loaded
│   ├── tailwind.cdn.js          # Tailwind CSS (403KB)
│   └── htmx.min.js             # HTMX (47KB)
└── ionicons/
    └── dist/ionicons/           # Iconos completos (20MB con SVGs)
        ├── ionicons.esm.js
        ├── ionicons.js
        └── svg/                 # 1300+ iconos SVG
```

✅ **100% Offline** - Sin dependencias de CDN
✅ **Rápido** - Sin latencia de red
✅ **Confiable** - Funciona sin internet

## Tailwind CSS + Ionic Integration

El archivo `tailwind-ionic.css` proporciona utilidades Tailwind que usan variables de Ionic para seamless theming:

### Colores con Ionic Variables

```html
<!-- Text colors -->
<div class="text-primary">Primary color text</div>
<div class="text-success">Success text</div>
<div class="text-danger">Danger text</div>

<!-- Background colors -->
<div class="bg-primary">Primary background</div>
<div class="bg-card">Card background (adapts to theme)</div>
<div class="bg-muted">Muted background</div>

<!-- Con opacidad -->
<div class="bg-primary/10">10% opacity primary</div>
```

### Componentes Pre-styled

```html
<!-- Buttons with Ionic colors -->
<button class="btn-primary px-4 py-2">Primary Button</button>
<button class="btn-success px-4 py-2">Success Button</button>

<!-- Cards -->
<div class="card-ionic p-4 shadow-ionic-md">
  Card with Ionic theme colors
</div>

<!-- Inputs -->
<input class="input-ionic px-3 py-2 w-full" placeholder="Input with theme">
```

### Border Radius con Ionic

```html
<div class="rounded-ionic">Uses --radius variable</div>
<div class="rounded-ionic-sm">Smaller radius</div>
<div class="rounded-ionic-lg">Larger radius</div>
```

### Ventajas

✅ **Seamless theming**: Colores cambian automáticamente con el tema
✅ **Dark mode support**: Se adapta automáticamente a `body.dark`
✅ **Consistencia**: Usa las mismas variables que Ionic components
✅ **Flexibilidad**: Combina poder de Tailwind con colores de Ionic

## Collectstatic

En producción, Django recolecta todos los archivos estáticos:

```bash
python manage.py collectstatic
```

Esto copia archivos de:
- `static/` (este directorio)
- `apps/*/static/` (static de cada app)

A: `staticfiles/` (configurado en `STATIC_ROOT`)
