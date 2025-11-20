# Empty State Component

Componente para mostrar estados vacíos (sin datos) con icono, mensaje y acción opcional.

## Uso

```django
{% include 'components/empty_state/empty_state.html' with
    icon="cube-outline"
    title="No Hubs Registered"
    message="You haven't registered any hubs yet. Register your first hub to get started."
    action_url="/hubs/register/"
    action_icon="add-outline"
    action_label="Register First Hub"
%}
```

## Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `icon` | string | ❌ No | Nombre del ion-icon (default: "information-circle-outline") |
| `title` | string | ✅ Sí | Título del estado vacío |
| `message` | string | ✅ Sí | Mensaje descriptivo |
| `action_url` | string | ❌ No | URL del botón de acción (si no se proporciona, no se muestra botón) |
| `action_icon` | string | ❌ No | Icono del botón de acción |
| `action_label` | string | ❌ No | Texto del botón (default: "Get Started") |

## Ejemplos

### Solo mensaje (sin acción)
```django
{% include 'components/empty_state/empty_state.html' with
    icon="search-outline"
    title="No Results Found"
    message="Try adjusting your search filters"
%}
```

### Con acción
```django
{% include 'components/empty_state/empty_state.html' with
    icon="cloud-download-outline"
    title="No Plugins Installed"
    message="Browse the marketplace to discover and install plugins"
    action_url="/plugins/marketplace/"
    action_label="Browse Marketplace"
%}
```

## Clases Tailwind Usadas

- `text-center` - Centrado de texto
- `py-12 px-8` - Padding vertical 3rem, horizontal 2rem
- `text-6xl` - Icono grande (4rem)
- `text-medium` - Color medium de Ionic
- `mb-4`, `mb-2`, `mb-6` - Margins

## Ubicaciones de Uso

- Cloud: hub_list, marketplace, installed plugins, my_plugins, profile
- Hub: plugins, employees, future templates
