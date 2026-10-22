# Peticiones de `apps/staff` a `@erplora/ui`

**Estado al cerrar la app (CLOSE-STAFF, 2026-10-22):** contra `ERPlora/ui` `origin/main` de635ff (el puntero
del Hub está en 07b4392):

- **`SearchSelect`** ha llegado como `Combo` (ya está en 07b4392, el puntero del Hub) y Personal lo usa en sus
  cuatro selectores; su copia propia se ha borrado (CLOSE-STAFF, segunda vuelta).
- **Fecha y hora** y la **tarjeta de cifra** siguen abiertas: ninguna ha llegado a `ui`. Sus sustitutos
  funcionan y ningún flujo está roto; van propuestas para `## 6` de `MIGRATION.md` como
  `staff:ui-time-date-fields` (la misma petición que `schedule:ui-time-date-fields`) y `staff:ui-kpi-card`.

## Iconos

Ninguna pendiente: `ion:shield-outline` (pestaña «Roles», el icono del módulo viejo) ya está registrado
en `packages/ui` (8c30c2a) y lo usan el menú (`apps/staff/apps.py`) y la barra de pestañas.
`ion:ban-outline` («Desactivar», «Cancelar» ausencia) también.

## Componentes

### `SearchSelect` — selector con búsqueda en el servidor (cerrada: llegó como `Combo`)

- **Para qué:** elegir en una lista que puede pasar de las 100 filas que da el servidor de una vez
  (miembros del equipo, roles, cuentas del negocio). Un `ion-select` con `limit: 100` se queda corto.
- **Uso en staff:** «Rol» y «Usuario del Hub» de la ficha y «Miembro» de la ausencia y de Horarios son
  `Combo` con `search` (`frontend/lib/pickers.ts`). «Sin rol» y «Sin acceso al Hub» siguen siendo la
  primera opción mientras no se teclea (`asCombo`), como en el `ion-select` viejo, y sin botón de vaciar;
  «Miembro» es obligatorio y tampoco lo lleva. Los filtros «Rol», «Usuario del Hub» y «Miembro» son el
  `lookup` del embudo de `DataTable`, con las mismas búsquedas.

### Fecha y hora en el orden del idioma del negocio

- **Para qué:** el módulo viejo pintaba y leía las fechas (`dd/mm/aaaa` en español) y las horas (24 h)
  con campos de texto propios (staff#86, staff#87), porque `<input type="date|time">` usa el orden del
  sistema operativo y no el del Hub. Mientras no exista, staff usa `ion-input type="date|time"`, como
  tax: en un Chrome en inglés con el Hub en español, el campo enseña `mm/dd/yyyy`.
- **API propuesta:** `DateField` / `TimeField` con `v-model` en ISO (`YYYY-MM-DD`, `HH:MM`), `label`,
  `errorText`, y lectura de lo tecleado en el orden de `<html lang>` (también `05102026` y la ISO).
- **Y un formateador** `formatDate(iso, locale)` en `@erplora/ui/components/format` para los días de
  calendario (en UTC, sin desplazar un día), junto a `formatDateTime`; staff lo tiene en
  `frontend/lib/format.ts`.

### Tarjeta de cifra (el `ok-kpi` del producto actual)

- **Para qué:** las cifras de Personal (STAFF-F23: «Plantilla activa», «Ausentes hoy», «Ausencias
  pendientes») son los paneles del Inicio viejo dentro de la app. `frontend/components/StaffFigures.vue`
  rehace la tarjeta (etiqueta en mayúsculas sobre la cifra grande, «…» mientras llega), igual que
  `CustomerStats.vue` de Clientes: con una compartida se borran las dos copias.
- **API propuesta:** `KpiCard` con `label`, `value` (texto ya formateado; `undefined` = «…») y
  `testid`, y un `KpiGroup` (rejilla, `role="group"`, `aria-busy`) que en el móvil ponga hasta tres en
  una línea.
