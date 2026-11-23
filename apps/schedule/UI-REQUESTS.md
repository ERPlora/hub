# Peticiones de `apps/schedule` a `@erplora/ui`

Lo que las páginas de Horarios necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Ya en `@erplora/ui`, sin usar todavía

- `ion:star-outline` — pestaña y entrada de menú **Días especiales** (`apps.py`): es el
  icono del módulo viejo (`star-outline` en su `navigation`), ya registrado en `packages/ui/src/shell/icons.ts`
  (lo usa Servicios desde `FIX-UI-SHELL-ICONS-SERVICE-TASK`). Hoy: `ion:calendar-outline`. Al usarlo, cambiar
  `apps.py` (`navigation`) y sus tests (`tests/test_apps.py`): las pestañas pintan el icono del menú.

## Formateadores

### Una hora y una fecha en el reloj y el orden del idioma del Hub

- **Para qué:** las tablas de Horarios enseñan horas (`14:30`, `2:30 PM`) y fechas (`dd/mm/aaaa` en español)
  sin que la zona del dispositivo mueva un día.
- **API propuesta:** dos formateadores en `@erplora/ui/components/format`, junto a `formatDateTime`:
  `formatTime(HH:MM, locale)` (el reloj del idioma, sin zona) y `formatDate(YYYY-MM-DD, locale)` (en UTC, sin
  mover un día). Horarios los tiene en `frontend/lib/format.ts`.
