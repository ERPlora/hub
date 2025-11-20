# Status Badge Component

Badge de estado con colores success/danger basado en condición booleana.

## Uso

```django
{% include 'components/status_badge/status_badge.html' with
    is_active=hub.is_online
    active_label="Online"
    inactive_label="Offline"
%}
```

## Parámetros

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `is_active` | boolean | ✅ Sí | Condición que determina el estado (True = success, False = danger) |
| `active_label` | string | ❌ No | Texto cuando `is_active` es True (default: "Active") |
| `inactive_label` | string | ❌ No | Texto cuando `is_active` es False (default: "Inactive") |

## Ejemplos

### Hub Online/Offline
```django
{% include 'components/status_badge/status_badge.html' with
    is_active=hub.is_online
    active_label="Online"
    inactive_label="Offline"
%}
```

### Plugin Active/Inactive
```django
{% include 'components/status_badge/status_badge.html' with
    is_active=plugin.is_active
    active_label="Active"
    inactive_label="Inactive"
%}
```

### Defaults (Active/Inactive)
```django
{% include 'components/status_badge/status_badge.html' with
    is_active=item.status
%}
```

### Payment Status (Paid/Unpaid)
```django
{% include 'components/status_badge/status_badge.html' with
    is_active=invoice.is_paid
    active_label="Paid"
    inactive_label="Unpaid"
%}
```

## Colores

- `is_active=True` → `color="success"` (verde)
- `is_active=False` → `color="danger"` (rojo)

## Ubicaciones de Uso

- Cloud: hub_list (Online/Offline badges)
- Cloud: marketplace (status de plugins)
- Hub: plugins (Active/Inactive)
