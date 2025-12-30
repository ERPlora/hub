# UI Components

Sistema de componentes Django que encapsula Ionic internamente. Las vistas usan tags simples sin necesidad de conocer los detalles de Ionic.

## Uso

```html
{% load ui %}

{# Botones #}
{% ui_button "Guardar" color="primary" icon="save-outline" %}
{% ui_button "Cancelar" color="medium" fill="outline" %}
{% ui_icon_button "trash-outline" color="danger" %}

{# Cards estadísticas #}
{% ui_stat_card value="$12,450" label="Ventas Hoy" icon="trending-up-outline" color="success" %}

{# Inputs #}
{% ui_input name="email" label="Email" type="email" required=True %}
{% ui_textarea name="notes" label="Notas" rows=4 %}
{% ui_select name="category" label="Categoría" options=categories %}

{# Toggles y Checkboxes #}
{% ui_toggle name="active" label="Activo" checked=True %}
{% ui_checkbox name="terms" label="Acepto los términos" %}

{# Badges #}
{% ui_badge "Nuevo" color="success" %}
{% ui_status_badge "active" %}

{# Avatar #}
{% ui_avatar src=user.avatar size="lg" %}
{% ui_avatar initials="JD" color="primary" %}

{# Empty State #}
{% ui_empty_state title="No hay productos" description="Añade tu primer producto" icon="cube-outline" action_label="Añadir" action_url="/products/new/" %}

{# Grid Layout #}
{% ui_grid_start %}
{% ui_row_start %}
    {% ui_col_start size="12" size_md="6" size_lg="3" %}
        <!-- Contenido -->
    {% ui_col_end %}
{% ui_row_end %}
{% ui_grid_end %}
```

## Componentes Disponibles

### Botones
- `ui_button` - Botón con texto y/o icono
- `ui_icon_button` - Botón solo icono

### Cards
- `ui_card` - Card genérica
- `ui_stat_card` - Card para estadísticas/KPIs

### Forms
- `ui_input` - Campo de texto
- `ui_textarea` - Área de texto
- `ui_select` - Selector desplegable
- `ui_checkbox` - Casilla de verificación
- `ui_toggle` - Interruptor

### Lists
- `ui_list_item` - Elemento de lista

### Badges
- `ui_badge` - Badge genérico
- `ui_chip` - Chip con icono opcional
- `ui_status_badge` - Badge de estado (active, inactive, pending, etc.)

### Layout
- `ui_page_header` - Header de página con back button
- `ui_avatar` - Avatar con imagen o iniciales
- `ui_empty_state` - Estado vacío
- `ui_spinner` - Spinner de carga
- `ui_skeleton` - Skeleton loading
- `ui_modal` - Modal

### Grid
- `ui_grid_start` / `ui_grid_end`
- `ui_row_start` / `ui_row_end`
- `ui_col_start` / `ui_col_end`

## Propiedades HTMX

Todos los componentes interactivos soportan:
- `hx_get` - URL para GET
- `hx_post` - URL para POST
- `hx_target` - Selector del target
- `hx_swap` - Método de swap
- `hx_push_url` - Push URL al historial

## Responsive Grid

Usa ion-grid con breakpoints:
- `size="12"` - Móvil (100%)
- `size_sm="6"` - >576px (50%)
- `size_md="4"` - >768px (33%)
- `size_lg="3"` - >992px (25%)
- `size_xl="2"` - >1200px (16.6%)
