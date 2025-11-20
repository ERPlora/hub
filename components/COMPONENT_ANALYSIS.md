# Análisis de Componentes - Cloud & Hub

**Objetivo:** Identificar patrones HTML duplicados dentro de Cloud y Hub (por separado) para valorar si vale la pena crear componentes reutilizables.

**Criterio:** Solo incluir patrones que se repiten **3+ veces** en el mismo proyecto.

---

## 📦 CLOUD - Componentes Candidatos

### 1. Stat Card (Tarjeta de Estadística)

**Patrón repetido:**
```html
<ion-card>
    <ion-card-content>
        <div style="font-size: 2rem; font-weight: 700; color: var(--ion-color-primary);">
            {{ number }}
        </div>
        <div style="color: var(--ion-color-medium); margin-top: 4px;">
            {{ label }}
        </div>
    </ion-card-content>
</ion-card>
```

**Ubicaciones (6 ocurrencias):**
- `apps/dashboard/hubs/templates/hubs/pages/hub_list.html` (3x: Total Hubs, Online, Offline)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/marketplace.html` (3x: Plugin stats)

**Parámetros necesarios:**
- `value` (número o texto)
- `label` (texto descriptivo)
- `color` (opcional: primary, success, danger)

**¿Vale la pena?**
- ✅ **SÍ** - 6 ocurrencias, patrón idéntico
- 🎯 Ahorro: ~60 líneas de código
- 💡 Facilita cambios de diseño futuros

---

### 2. Hub/Plugin Card (Tarjeta de Item con Acciones)

**Patrón repetido:**
```html
<ion-card>
    <ion-card-content>
        <!-- Icon/Badge + Title + Subtitle -->
        <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
            <ion-icon name="..." style="font-size: 40px; color: var(--ion-color-primary);"></ion-icon>
            <div>
                <h3>{{ title }}</h3>
                <p style="color: var(--ion-color-medium);">{{ subtitle }}</p>
            </div>
            <ion-badge color="...">{{ status }}</ion-badge>
        </div>

        <!-- Grid de metadata -->
        <ion-grid>
            <ion-row>
                <ion-col size="6">
                    <div style="color: var(--ion-color-medium); font-size: 0.875rem;">{{ key }}</div>
                    <div>{{ value }}</div>
                </ion-col>
                <!-- ... más columnas -->
            </ion-row>
        </ion-grid>

        <!-- Action buttons -->
        <div style="display: flex; gap: 0.5rem; margin-top: 1rem;">
            <ion-button>{{ action }}</ion-button>
        </div>
    </ion-card-content>
</ion-card>
```

**Ubicaciones (5+ ocurrencias):**
- `apps/dashboard/hubs/templates/hubs/pages/hub_list.html` (lista de hubs)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/marketplace.html` (lista de plugins)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/installed.html` (plugins instalados)

**Parámetros necesarios:**
- `icon` (nombre del ion-icon)
- `title` (título principal)
- `subtitle` (subtítulo)
- `status_badge` (opcional: texto + color)
- `metadata` (dict de key-value pairs)
- `actions` (lista de botones)

**¿Vale la pena?**
- 🤔 **DEPENDE** - Patrón complejo con mucha variación
- ⚠️ Riesgo: Demasiados parámetros = difícil de usar
- 💡 Alternativa: Crear sub-componentes (card_header, card_metadata, card_actions)

---

### 3. Empty State (Estado Vacío)

**Patrón repetido:**
```html
<ion-card>
    <ion-card-content style="text-align: center; padding: 3rem 2rem;">
        <ion-icon name="{{ icon }}" style="font-size: 4rem; color: var(--ion-color-medium); margin-bottom: 1rem;"></ion-icon>
        <h3 style="color: var(--ion-color-medium);">{{ title }}</h3>
        <p style="color: var(--ion-color-medium); margin-bottom: 1.5rem;">{{ message }}</p>
        <ion-button href="{{ action_url }}">{{ action_label }}</ion-button>
    </ion-card-content>
</ion-card>
```

**Ubicaciones (5 ocurrencias):**
- `apps/dashboard/hubs/templates/hubs/pages/hub_list.html` (No hubs registered)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/marketplace.html` (No plugins found)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/installed.html` (No plugins installed)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/my_plugins.html` (No plugins published)
- `apps/dashboard/profile/templates/dashboard/profile/pages/index.html` (posible uso futuro)

**Parámetros necesarios:**
- `icon` (ion-icon name)
- `title` (título del estado vacío)
- `message` (descripción)
- `action_url` (opcional: URL del botón)
- `action_label` (opcional: texto del botón)

**¿Vale la pena?**
- ✅ **SÍ** - 5 ocurrencias, patrón 100% idéntico
- 🎯 Ahorro: ~75 líneas de código
- 💡 Super reutilizable, parámetros simples

---

### 4. Page Header (Encabezado de Página)

**Patrón repetido:**
```html
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
    <div>
        <h2>{{ title }}</h2>
        <p style="color: var(--ion-color-medium);">{{ subtitle }}</p>
    </div>
    <ion-button href="{{ action_url }}">
        <ion-icon slot="start" name="{{ action_icon }}"></ion-icon>
        {{ action_label }}
    </ion-button>
</div>
```

**Ubicaciones (16+ ocurrencias):**
- Prácticamente **TODOS** los templates de dashboard (hubs, plugins, profile, overview)
- Ejemplos:
  - `hubs/pages/hub_list.html` ("My Hubs" + "Register Hub")
  - `plugins/pages/marketplace.html` ("Marketplace" + "Install Queue")
  - `profile/pages/index.html` ("Profile Settings" + "Export Data")

**Parámetros necesarios:**
- `title` (título de página)
- `subtitle` (opcional: descripción)
- `action_url` (opcional: URL del botón)
- `action_icon` (opcional: ion-icon name)
- `action_label` (opcional: texto del botón)

**¿Vale la pena?**
- ✅ **SÍ 100%** - 16+ ocurrencias, super repetido
- 🎯 Ahorro: ~200 líneas de código
- 💡 Este es el componente más valioso

---

### 5. Form Section Card (Card de Formulario)

**Patrón repetido:**
```html
<ion-card>
    <ion-card-header>
        <ion-card-title>{{ section_title }}</ion-card-title>
    </ion-card-header>
    <ion-card-content>
        <form method="post">
            {% csrf_token %}
            <ion-list>
                <ion-item>
                    <ion-input label="{{ label }}" label-placement="floating" name="{{ name }}" value="{{ value }}"></ion-input>
                </ion-item>
                <!-- ... más campos -->
            </ion-list>
            <ion-button type="submit" expand="block">{{ submit_label }}</ion-button>
        </form>
    </ion-card-content>
</ion-card>
```

**Ubicaciones (6+ ocurrencias):**
- `apps/dashboard/profile/templates/dashboard/profile/pages/index.html` (3x: Personal Info, Billing, Security)
- `apps/dashboard/hubs/templates/hubs/pages/hub_settings.html` (2x: Hub Settings, Store Config)
- `apps/dashboard/profile/templates/dashboard/profile/pages/change_password.html` (1x: Change Password)

**Parámetros necesarios:**
- `section_title` (título del card)
- `form_content` (contenido del form - usar {% block %})
- `submit_label` (texto del botón submit)

**¿Vale la pena?**
- 🤔 **DEPENDE** - Contenido del form varía mucho
- 💡 Mejor opción: Template tag `{% form_section %}` en lugar de include
- ⚠️ Alternativa: Solo crear card wrapper, dejar form content como slot

---

### 6. Filter Chips (Chips de Filtro)

**Patrón repetido:**
```html
<div style="display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap;">
    <ion-chip :color="filter === 'all' ? 'primary' : ''" @click="filter = 'all'">
        <ion-label>All</ion-label>
    </ion-chip>
    <ion-chip :color="filter === 'value' ? 'primary' : ''" @click="filter = 'value'">
        <ion-label>{{ label }}</ion-label>
    </ion-chip>
    <!-- ... más chips -->
</div>
```

**Ubicaciones (3 ocurrencias):**
- `apps/dashboard/hubs/templates/hubs/pages/hub_list.html` (All, Online, Offline)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/marketplace.html` (All, Free, Premium)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/installed.html` (All, Active, Inactive)

**Parámetros necesarios:**
- `filters` (lista de {value, label})
- `current_filter` (Alpine.js variable name)

**¿Vale la pena?**
- 🤔 **BORDERLINE** - 3 ocurrencias, depende de Alpine.js
- 💡 Mejor como Alpine.js component que template
- ⚠️ Requiere pasar data structure complejo

---

### 7. Status Badge (Badge de Estado)

**Patrón repetido:**
```html
<ion-badge color="{% if hub.is_online %}success{% else %}danger{% endif %}">
    {% if hub.is_online %}Online{% else %}Offline{% endif %}
</ion-badge>
```

**Ubicaciones (4+ ocurrencias):**
- `apps/dashboard/hubs/templates/hubs/pages/hub_list.html` (2x: Online/Offline badges)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/installed.html` (2x: Active/Inactive)

**Parámetros necesarios:**
- `status` (boolean o string: 'online', 'active', etc.)
- `labels` (opcional: dict de {true: 'Online', false: 'Offline'})

**¿Vale la pena?**
- ✅ **SÍ** - Simple, reutilizable, 4+ ocurrencias
- 🎯 Ahorro: ~15 líneas de código
- 💡 Template tag sería mejor: `{% status_badge hub.is_online %}`

---

### 8. Modal de Instalación (Install/Action Modal)

**Patrón repetido:**
```html
<ion-modal trigger="modal-id" :is-open="modalOpen" @didDismiss="modalOpen = false">
    <ion-header>
        <ion-toolbar>
            <ion-title>{{ title }}</ion-title>
            <ion-buttons slot="end">
                <ion-button @click="closeModal()">Close</ion-button>
            </ion-buttons>
        </ion-toolbar>
    </ion-header>
    <ion-content class="ion-padding">
        <!-- Contenido específico -->
    </ion-content>
</ion-modal>
```

**Ubicaciones (4 ocurrencias):**
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/marketplace.html` (2x: Install modal, Cart modal)
- `apps/dashboard/hubs/templates/hubs/pages/hub_list.html` (1x: Register hub modal)
- `apps/dashboard/profile/templates/dashboard/profile/pages/delete_confirm.html` (1x: Delete confirm modal)

**Parámetros necesarios:**
- `modal_id` (trigger ID)
- `title` (título del modal)
- `content` (slot para contenido)

**¿Vale la pena?**
- 🤔 **DEPENDE** - Contenido varía mucho
- 💡 Mejor crear base modal wrapper, contenido como slot
- ⚠️ Requiere Alpine.js integration

---

### 9. Toast Notification Helper (JavaScript)

**Patrón repetido:**
```javascript
const toast = document.createElement('ion-toast');
toast.message = '...';
toast.duration = 2000;
toast.color = 'success';
document.body.appendChild(toast);
await toast.present();
```

**Ubicaciones (10+ ocurrencias):**
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/marketplace.html` (5x: add to cart, remove, install, etc.)
- `apps/dashboard/profile/templates/dashboard/profile/pages/index.html` (2x: save success, error)
- `apps/dashboard/hubs/templates/hubs/pages/hub_list.html` (2x: register success, error)

**Parámetros necesarios:**
- `message` (texto)
- `color` (success, danger, warning, info)
- `duration` (opcional: default 2000ms)

**¿Vale la pena?**
- ✅ **SÍ 100%** - 10+ ocurrencias, patrón idéntico
- 🎯 Ahorro: ~80 líneas de código
- 💡 Crear helper JS: `showToast(message, color, duration)`

---

### 10. Plugin/Hub Grid Layout

**Patrón repetido:**
```html
<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 1.5rem;">
    <!-- Cards aquí -->
</div>
```

**Ubicaciones (3 ocurrencias):**
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/marketplace.html` (plugin grid)
- `apps/dashboard/plugins/templates/dashboard/plugins/pages/installed.html` (installed plugins)
- `apps/dashboard/hubs/templates/hubs/pages/hub_list.html` (hubs grid)

**Parámetros necesarios:**
- `min_width` (opcional: default 350px)
- `gap` (opcional: default 1.5rem)

**¿Vale la pena?**
- 🤔 **NO** - Mejor crear clase CSS `.grid-layout`
- 💡 Añadir a `static/css/dashboard.css` en lugar de componente

---

## 📦 HUB - Componentes Candidatos

### 1. Stat Card (idéntico a Cloud)

**Ubicaciones (3 ocurrencias):**
- `hub/apps/core/templates/core/plugins.html` (3x: Installed, Active, Discovered)

**¿Vale la pena?**
- ✅ **SÍ** - Mismo patrón que Cloud, reutilizable

---

### 2. Plugin Card (similar a Cloud)

**Ubicaciones (2 ocurrencias):**
- `hub/apps/core/templates/core/plugins.html` (installed plugins list)
- `hub/plugins/products/templates/products/index.html` (product cards - posible)

**¿Vale la pena?**
- 🤔 **DEPENDE** - Solo 2 ocurrencias, evaluar caso por caso

---

### 3. Empty State (idéntico a Cloud)

**Ubicaciones (3 ocurrencias):**
- `hub/apps/core/templates/core/plugins.html` (No plugins installed)
- `hub/apps/core/templates/core/employees.html` (No employees)
- Futuros templates (products, sales, etc.)

**¿Vale la pena?**
- ✅ **SÍ** - Patrón idéntico a Cloud

---

### 4. Page Header (idéntico a Cloud)

**Ubicaciones (9+ ocurrencias):**
- Prácticamente todos los templates de Hub (dashboard, plugins, settings, employees, pos)

**¿Vale la pena?**
- ✅ **SÍ 100%** - El componente más repetido

---

### 5. Form Section Card (similar a Cloud)

**Ubicaciones (6 ocurrencias):**
- `hub/apps/core/templates/core/settings.html` (3x: Hub Config, Store Config, Display Settings)
- Futuros templates de configuración

**¿Vale la pena?**
- 🤔 **DEPENDE** - Mismo dilema que Cloud

---

### 6. Toast Notification Helper (JavaScript - idéntico a Cloud)

**Ubicaciones (8+ ocurrencias):**
- `hub/apps/core/templates/core/plugins.html` (4x: install, activate, deactivate, uninstall)
- `hub/apps/core/templates/core/settings.html` (3x: save success, errors)
- Otros templates

**¿Vale la pena?**
- ✅ **SÍ 100%** - Mismo helper que Cloud, compartible

---

## 🎯 RESUMEN - ¿Qué Componentes Crear?

### ✅ CREAR (Alta Prioridad - Impacto Inmediato)

| Componente | Cloud | Hub | Total | Ahorro Estimado |
|------------|-------|-----|-------|-----------------|
| **page_header.html** | 16x | 9x | 25x | ~200 líneas |
| **empty_state.html** | 5x | 3x | 8x | ~100 líneas |
| **stat_card.html** | 6x | 3x | 9x | ~90 líneas |
| **showToast() JS** | 10x | 8x | 18x | ~120 líneas |
| **status_badge.html** | 4x | 2x | 6x | ~20 líneas |

**Total Fase 1:** ~530 líneas eliminadas, 5 componentes

---

### 🤔 EVALUAR (Media Prioridad - Requiere Análisis)

| Componente | Razón |
|------------|-------|
| **item_card.html** | Demasiados parámetros, mejor sub-componentes |
| **form_section.html** | Contenido muy variable, mejor template tag |
| **install_modal.html** | Contenido específico, mejor base modal + slots |
| **filter_chips.html** | Solo 3 ocurrencias, depende de Alpine.js |

---

### ❌ NO CREAR (Mejor Alternativa CSS)

| Componente | Alternativa |
|------------|-------------|
| **grid_layout** | Clase CSS `.grid-responsive` |
| **modal base** | Ya existe `ion-modal` de Ionic |

---

## 📋 RECOMENDACIÓN FINAL

### Estrategia de Implementación:

**FASE 1: Quick Wins (2-3 horas)**
1. ✅ Crear `/cloud/components/page_header.html`
2. ✅ Crear `/cloud/components/empty_state.html`
3. ✅ Crear `/cloud/components/stat_card.html`
4. ✅ Crear `/cloud/static/js/toast-helper.js`
5. ✅ Crear `/cloud/components/status_badge.html`

**FASE 2: Hub Sync (1 hora)**
- Copiar componentes de Cloud → Hub
- Ajustar paths si es necesario

**FASE 3: Refactorizar Templates (4-5 horas)**
- Reemplazar código duplicado con `{% include 'components/...' %}`
- Testing visual en navegador

---

## 🚀 Próximos Pasos

1. **Validar esta lista** con el equipo/usuario
2. **Decidir** si procedemos con FASE 1
3. **Crear** estructura de carpetas `/components/`
4. **Implementar** componentes uno por uno
5. **Refactorizar** templates existentes
6. **Documentar** uso en README.md

---

**Fecha:** 2025-11-19
**Estado:** Pendiente aprobación para empezar FASE 1
