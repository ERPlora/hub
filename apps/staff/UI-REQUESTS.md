# Peticiones de `apps/staff` a `@erplora/ui`

## Iconos

Ninguna pendiente: `ion:shield-outline` (pestaña «Roles», el icono del módulo viejo) ya está registrado
en `packages/ui` (8c30c2a) y lo usan el menú (`apps/staff/apps.py`) y la barra de pestañas.
`ion:ban-outline` («Desactivar», «Cancelar» ausencia) también.

## Componentes

### `SearchSelect` — selector con búsqueda en el servidor

- **Para qué:** elegir en una lista que puede pasar de las 100 filas que da el servidor de una vez
  (miembros del equipo, roles, cuentas del negocio). Un `ion-select` con `limit: 100` se queda corto.
- **API propuesta** (la de `apps/staff/frontend/components/SearchSelect.vue`, que hace de puente):
  props `label`, `value` (`''` = ninguno), `display` (la etiqueta del valor elegido), `noneLabel?`
  (opción vacía primera: «Sin rol», «Sin acceso al Hub», «Cualquiera»), `load(search) =>
  Promise<{ value, label }[]>`, `errorText?`, `disabled?`, `testid`; emite `update:value(value,
  label)`. Campo con caja como el `ion-select` (`fill="outline"`, `mode="md"`) que abre un
  `FormModal` con `ion-searchbar` (debounce 300 ms), la lista, «Cargando…», «Sin resultados» y el
  error; una respuesta tardía de una búsqueda vieja no pisa la nueva.
- **Uso en staff:** «Rol» y «Usuario del Hub» de la ficha; «Miembro» de la ausencia y de Horarios;
  filtros «Rol», «Usuario del Hub» y «Miembro». Tax tiene otro igual: con el compartido se borran los
  dos.

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

### Filtros por columna en `DataTable`

- **Para qué:** el `ok-data-table` viejo filtraba por columna en su panel lateral. Staff (como tax) lo
  suple con `frontend/components/FilterPanel.vue` en el slot `filters`: botón «Filtros» con contador y
  un `FormModal` con un control por filtro (texto, lista cerrada con «Cualquiera», `SearchSelect`,
  rango de números o de fechas).
- **API propuesta:** `filters` en la columna (`{ kind: 'text' | 'select' | 'search' | 'range', … }`) y
  `v-model:filters` en la tabla; con eso se borran los `FilterPanel` de cada app.
