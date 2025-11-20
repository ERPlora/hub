# Components Library - ERPlora

Librería de componentes reutilizables para Cloud y Hub usando Django includes.

## 📦 Componentes Disponibles

| Componente | Descripción | Uso | Ahorro |
|------------|-------------|-----|--------|
| [page_header](page_header/) | Header de página con título y acción | 25x | ~200 líneas |
| [empty_state](empty_state/) | Estado vacío con icono y mensaje | 8x | ~100 líneas |
| [stat_card](stat_card/) | Tarjeta de estadística | 9x | ~90 líneas |
| [status_badge](status_badge/) | Badge de estado (success/danger) | 6x | ~20 líneas |
| [toast_helper](toast_helper/) | Helper JS para notificaciones | 18x | ~120 líneas |

**Total:** ~530 líneas de código eliminadas

---

## 🚀 Instalación y Uso

### 1. En Templates Django

Incluir componentes con `{% include %}`:

```django
{% include 'components/page_header/page_header.html' with
    title="My Page"
    action_url="/action/"
    action_label="Do Something"
%}
```

### 2. JavaScript Helper

Incluir el script en el template:

```django
{% load static %}
<script src="{% static 'js/toast-helper.js' %}"></script>

<script>
// Usar en Alpine.js o JavaScript
Toast.success('Operation successful!');
</script>
```

---

## 📚 Guía Rápida por Componente

### Page Header

```django
{% include 'components/page_header/page_header.html' with
    title="Dashboard"
    subtitle="Welcome back"
    action_url="/settings/"
    action_icon="settings-outline"
    action_label="Settings"
%}
```

### Empty State

```django
{% include 'components/empty_state/empty_state.html' with
    icon="cube-outline"
    title="No Items Found"
    message="Get started by creating your first item"
    action_url="/items/create/"
    action_label="Create Item"
%}
```

### Stat Card

```django
{% include 'components/stat_card/stat_card.html' with
    value=total_count
    label="Total Items"
    color="primary"
%}
```

### Status Badge

```django
{% include 'components/status_badge/status_badge.html' with
    is_active=item.is_active
    active_label="Active"
    inactive_label="Inactive"
%}
```

### Toast Notifications

```javascript
// Success
Toast.success('Saved successfully!');

// Error
Toast.error('Failed to save');

// Warning
Toast.warning('Connection unstable');

// Custom
showToast('Custom message', 'primary', 3000, 'top');
```

---

## 🎨 Diseño y Estilos

Todos los componentes usan:
- ✅ **Ionic 8 Web Components** (ion-card, ion-text, ion-button, etc.)
- ✅ **Tailwind CSS** para utilidades (flex, text-center, mb-6, etc.)
- ✅ **Variables CSS de Ionic** (--ion-color-primary, --ion-color-medium, etc.)
- ✅ **Alpine.js compatible** (funcionan con x-data, @click, etc.)

---

## 📂 Estructura de Archivos

```
components/
├── README.md                      # Este archivo
├── COMPONENT_ANALYSIS.md          # Análisis de duplicación
│
├── page_header/
│   ├── page_header.html          # Template
│   └── README.md                 # Documentación
│
├── empty_state/
│   ├── empty_state.html
│   └── README.md
│
├── stat_card/
│   ├── stat_card.html
│   └── README.md
│
├── status_badge/
│   ├── status_badge.html
│   └── README.md
│
└── toast_helper/
    ├── toast-helper.js           # JavaScript helper
    └── README.md
```

---

## 🔄 Sincronización Cloud ↔ Hub

Para mantener los componentes sincronizados entre Cloud y Hub:

### Opción 1: Copiar manualmente
```bash
cp -r cloud/components/ hub/components/
```

### Opción 2: Symlink (recomendado para desarrollo)
```bash
cd hub/
ln -s ../cloud/components/ components
```

### Opción 3: Git submodule (para proyectos separados)
Si Cloud y Hub están en repos diferentes, usar Git submodule para compartir componentes.

---

## ✅ Templates Refactorizados

### Cloud
- [ ] `apps/dashboard/hubs/templates/hubs/pages/hub_list.html`
- [ ] `apps/dashboard/plugins/templates/dashboard/plugins/pages/marketplace.html`
- [ ] `apps/dashboard/plugins/templates/dashboard/plugins/pages/installed.html`
- [ ] `apps/dashboard/profile/templates/dashboard/profile/pages/index.html`
- [ ] `apps/dashboard/overview/templates/dashboard/overview/pages/index.html`

### Hub
- [ ] `hub/apps/core/templates/core/plugins.html`
- [ ] `hub/apps/core/templates/core/settings.html`
- [ ] `hub/apps/core/templates/core/dashboard.html`

---

## 🛠️ Contribuir

### Añadir Nuevo Componente

1. **Crear carpeta**:
   ```bash
   mkdir components/nuevo_componente
   ```

2. **Crear template**:
   ```html
   {# components/nuevo_componente/nuevo_componente.html #}
   <div>
       {{ param }}
   </div>
   ```

3. **Documentar**:
   Crear `README.md` con:
   - Descripción
   - Parámetros
   - Ejemplos de uso
   - Ubicaciones donde se usa

4. **Actualizar este README**:
   Añadir componente a la tabla de arriba

---

## 📊 Métricas

- **Componentes creados:** 5
- **Líneas de código eliminadas:** ~530
- **Templates afectados:** 48 (Cloud: 25, Hub: 18)
- **Reducción estimada:** 20% del código de templates

---

**Fecha:** 2025-11-19
**Estado:** ✅ Componentes creados y listos para usar
**Siguiente:** Copiar a Hub y refactorizar templates
