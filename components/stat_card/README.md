# Stat Card Component

Tarjeta de estadística con número grande y label descriptivo.

## Uso

```django
{% include 'components/stat_card/stat_card.html' with
    value="24"
    label="Online Hubs"
    color="success"
%}
```

## Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `value` | string/number | ✅ Sí | Valor de la estadística (número o texto) |
| `label` | string | ✅ Sí | Etiqueta descriptiva |
| `color` | string | ❌ No | Color de Ionic (primary, success, danger, warning, etc.) Default: "primary" |

## Ejemplos

### Básico (color primary por defecto)
```django
{% include 'components/stat_card/stat_card.html' with
    value=total_hubs
    label="Total Hubs"
%}
```

### Con color success
```django
{% include 'components/stat_card/stat_card.html' with
    value=online_hubs
    label="Online"
    color="success"
%}
```

### Con color danger
```django
{% include 'components/stat_card/stat_card.html' with
    value=offline_hubs
    label="Offline"
    color="danger"
%}
```

### Con texto en lugar de número
```django
{% include 'components/stat_card/stat_card.html' with
    value="$1,234"
    label="Monthly Revenue"
    color="success"
%}
```

## Clases Tailwind Usadas

- `text-center` - Centrado de texto
- `py-6` - Padding vertical 1.5rem
- `text-4xl font-bold` - Número grande y bold
- `text-{color}` - Color dinámico de Ionic (text-primary, text-success, etc.)
- `mt-1 text-sm` - Label con margin top y texto pequeño

## Ubicaciones de Uso

- Cloud: hub_list (3x: Total, Online, Offline)
- Cloud: marketplace (stats de plugins)
- Hub: plugins (3x: Installed, Active, Discovered)
