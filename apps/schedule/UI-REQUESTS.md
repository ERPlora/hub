# Peticiones de `apps/schedule` a `@erplora/ui`

Lo que las páginas de Horarios necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

**Estado al cerrar la app (CLOSE-SCHEDULE, 2026-10-22):** las dos peticiones siguen abiertas: ninguna ha
llegado a `ERPlora/ui` (`origin/main` 07b4392, el mismo commit que el puntero del Hub). Sus sustitutos
funcionan y ningún flujo está roto; van propuestas para `## 6` de `MIGRATION.md` como `schedule:ui-icons` y
`schedule:ui-time-date-fields`.

## Iconos

- `ion:star-outline` — pestaña y entrada de menú **Días especiales** (`frontend/tabs.ts`, `apps.py`): es el
  icono del módulo viejo (`star-outline` en su `navigation`). Hoy: `ion:calendar-outline`. Al registrarlo,
  cambiar a la vez `frontend/tabs.ts`, `apps.py` (`navigation`) y sus tests (`tests/test_apps.py`,
  `frontend/tabs.test.ts`), que exigen que menú y pestañas lleven el mismo icono. Servicios pide la misma
  estrella (`FIX-UI-SHELL-ICONS-SERVICE-TASK` de la cola): con ella registrada se cierran las dos.

## Componentes

### Fecha y hora en el orden y el reloj del idioma del Hub

- **Para qué:** el módulo viejo escribía y leía las horas (`14:30`, `2:30 pm`, `1430`) y las fechas
  (`dd/mm/aaaa` en español) con campos de texto propios (schedules#50, #54, #57), porque
  `<input type="time|date">` usa el reloj y el orden del sistema operativo, no los del Hub. Mientras no
  exista, Horarios usa `ion-input type="time|date"` (como Personal e Impuestos): en un Chrome en inglés con
  el Hub en español, el campo enseña AM/PM y `mm/dd/yyyy`.
- **API propuesta:** `TimeField` / `DateField` con `v-model` en ISO (`HH:MM`, `YYYY-MM-DD`), `label`,
  `errorText`, y lectura de lo tecleado en el reloj y el orden de `<html lang>` (también `1430` y
  `24122026`). Los mismos que piden `apps/staff`, `apps/appointment`, `apps/attendance` y
  `apps/online_booking` en su `UI-REQUESTS.md` (`online_booking:ui-date-field` ya está en `## 6`): con uno
  compartido se cierran todos.
- **Y dos formateadores** en `@erplora/ui/components/format`, junto a `formatDateTime`: `formatTime(HH:MM,
  locale)` (el reloj del idioma, sin zona) y `formatDate(YYYY-MM-DD, locale)` (en UTC, sin mover un día).
  Horarios los tiene en `frontend/lib/format.ts`.
