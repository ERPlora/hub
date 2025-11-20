# Page Header Component

Header de página reutilizable con título, subtítulo opcional y botón de acción opcional.

## Uso

```django
{% include 'components/page_header/page_header.html' with
    title="My Hubs"
    subtitle="Manage your point of sale terminals"
    action_url="/hubs/register/"
    action_icon="add-outline"
    action_label="Register Hub"
%}
```

## Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `title` | string | ✅ Sí | Título principal de la página |
| `subtitle` | string | ❌ No | Subtítulo o descripción (opcional) |
| `action_url` | string | ❌ No | URL del botón de acción (si no se proporciona, no se muestra botón) |
| `action_icon` | string | ❌ No | Nombre del ion-icon para el botón (ej: "add-outline") |
| `action_label` | string | ❌ No | Texto del botón (default: "Action") |

## Ejemplos

### Solo título
```django
{% include 'components/page_header/page_header.html' with
    title="Dashboard"
%}
```

### Título + subtítulo
```django
{% include 'components/page_header/page_header.html' with
    title="Profile Settings"
    subtitle="Manage your account preferences"
%}
```

### Título + acción completa
```django
{% include 'components/page_header/page_header.html' with
    title="Plugins"
    subtitle="Installed plugins and extensions"
    action_url="/plugins/marketplace/"
    action_icon="storefront-outline"
    action_label="Browse Marketplace"
%}
```

## Clases Tailwind Usadas

- `flex justify-between items-center` - Layout flexbox
- `mb-6` - Margin bottom (1.5rem)
- `text-2xl font-bold` - Título grande y bold
- `mt-1` - Margin top pequeño para subtítulo

## Ubicaciones de Uso

- Cloud: 16+ templates de dashboard
- Hub: 9+ templates
