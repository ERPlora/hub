# Peticiones de `apps/schedule` a `@erplora/ui`

Lo que las páginas de Horarios necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos

- `ion:star-outline` — pestaña y entrada de menú **Días especiales** (`frontend/tabs.ts`, `apps.py`): es el
  icono del módulo viejo (`star-outline` en su `navigation`). Hoy: `ion:calendar-outline`. Al registrarlo,
  cambiar a la vez `frontend/tabs.ts`, `apps.py` (`navigation`) y sus tests (`tests/test_apps.py`,
  `frontend/tabs.test.ts`), que exigen que menú y pestañas lleven el mismo icono.

## Componentes

### Fecha y hora en el orden y el reloj del idioma del Hub

- **Para qué:** el módulo viejo escribía y leía las horas (`14:30`, `2:30 pm`, `1430`) y las fechas
  (`dd/mm/aaaa` en español) con campos de texto propios (schedules#50, #54, #57), porque
  `<input type="time|date">` usa el reloj y el orden del sistema operativo, no los del Hub. Mientras no
  exista, Horarios usa `ion-input type="time|date"` (como Personal e Impuestos): en un Chrome en inglés con
  el Hub en español, el campo enseña AM/PM y `mm/dd/yyyy`.
- **API propuesta:** `TimeField` / `DateField` con `v-model` en ISO (`HH:MM`, `YYYY-MM-DD`), `label`,
  `errorText`, y lectura de lo tecleado en el reloj y el orden de `<html lang>` (también `1430` y
  `24122026`). Los mismos que pide `apps/staff/UI-REQUESTS.md`: con uno compartido se borran los tres.
- **Y dos formateadores** en `@erplora/ui/components/format`, junto a `formatDateTime`: `formatTime(HH:MM,
  locale)` (el reloj del idioma, sin zona) y `formatDate(YYYY-MM-DD, locale)` (en UTC, sin mover un día).
  Horarios los tiene en `frontend/lib/format.ts`.

### Filtro de rango de fechas en `DataTable`

- **Para qué:** el `ok-data-table` viejo filtraba Días especiales por fecha y Cambios temporales por sus
  dos fechas con un rango (`daterange`). Los filtros que ya trae `DataTable` toman un solo día (`date`) o
  un rango de números (`range`).
- **API propuesta:** `filter: { type: 'daterange' }` en la columna, con `<key>_from` y `<key>_to` como el
  `range` numérico.
- **Hoy:** `frontend/components/FilterPanel.vue` en el slot `filters` (botón «Filtros» con contador y un
  `FormModal` con un control por filtro), como en Personal e Impuestos. Se borra cuando llegue.
