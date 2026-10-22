# Peticiones de `apps/staff` a `@erplora/ui`

**Estado al cerrar la app (CLOSE-STAFF, 2026-10-22):** contra `ERPlora/ui` `origin/main` de635ff (el puntero
del Hub está en 07b4392):

- **`SearchSelect`** ha llegado como `Combo` (ya está en 07b4392, el puntero del Hub): busca en el servidor con
  `search(query)`, descarta la respuesta vieja y se vacía con su botón (en lugar de la opción «Sin rol» /
  «Sin acceso al Hub»). Personal sigue con su copia, que funciona: pasar sus selectores a `Combo` cambia lo
  que se ve y queda como línea `FIX:` del informe de CLOSE-STAFF, no como petición abierta.
- **Fecha y hora** y la **tarjeta de cifra** siguen abiertas: ninguna ha llegado a `ui`. Sus sustitutos
  funcionan y ningún flujo está roto; van propuestas para `## 6` de `MIGRATION.md` como
  `staff:ui-time-date-fields` (la misma petición que `schedule:ui-time-date-fields`) y `staff:ui-kpi-card`.

## Iconos

Ninguna pendiente: `ion:shield-outline` (pestaña «Roles», el icono del módulo viejo) ya está registrado
en `packages/ui` (8c30c2a) y lo usan el menú (`apps/staff/apps.py`) y la barra de pestañas.
`ion:ban-outline` («Desactivar», «Cancelar» ausencia) también.

## Componentes

### `SearchSelect` — selector con búsqueda en el servidor (llegó como `Combo`)

- **Para qué:** elegir en una lista que puede pasar de las 100 filas que da el servidor de una vez
  (miembros del equipo, roles, cuentas del negocio). Un `ion-select` con `limit: 100` se queda corto.
- **API propuesta** (la de `apps/staff/frontend/components/SearchSelect.vue`, que hace de puente):
  props `label`, `value` (`''` = ninguno), `display` (la etiqueta del valor elegido), `noneLabel?`
  (opción vacía primera: «Sin rol», «Sin acceso al Hub», «Cualquiera»), `load(search) =>
  Promise<{ value, label }[]>`, `errorText?`, `disabled?`, `testid`; emite `update:value(value,
  label)`. Campo con caja como el `ion-select` (`fill="outline"`, `mode="md"`) que abre un
  `FormModal` con `ion-searchbar` (debounce 300 ms), la lista, «Cargando…», «Sin resultados» y el
  error; una respuesta tardía de una búsqueda vieja no pisa la nueva.
- **Uso en staff:** «Rol» y «Usuario del Hub» de la ficha; «Miembro» de la ausencia y de Horarios.
  Los filtros «Rol», «Usuario del Hub» y «Miembro» ya son el `lookup` del embudo de `DataTable`. Tax
  tiene otro igual: con el compartido se borran los dos.

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
