# Horarios (`schedule`)

Cuándo está abierto el negocio: la semana habitual (cerrado, abierto 24 horas o uno o varios tramos, también
pasada la medianoche), los días especiales (un festivo, una vez o cada año) y los cambios temporales (unas
fechas seguidas con otro horario o cerradas). Es el horario del negocio, no el de cada profesional (eso es de
Personal); Citas y Reservas lo leen para no reservar con el negocio cerrado.

- **Estado**: completa (2026-10-22): los 13 flujos, `SCHEDULE-F01` … `F13`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **La semana** (F01–F03, F08, F12): siete filas fijas en el orden de «Semana empieza», un día se edita con
  sus tramos (hasta 12, ordenados, sin solaparse; 00:00–00:00 es 24 horas), nace con lunes a viernes de 09:00
  a 18:00 sin confirmar y se confirma con un toque o al guardar un día.
- **Días especiales y cambios temporales** (F04–F07, F13): crear, corregir y borrar (de verdad: la fecha
  queda libre); un día especial por fecha y dos cambios temporales nunca cubren el mismo día (409, también a
  la vez); la carga de golpe de hasta 366 días salta los malos con su motivo.
- **¿Abierto?** (F09–F11): todo se lee con el reloj de pared del negocio; precedencia día especial exacto →
  anual → cambio temporal → semana → nada (`no_hours`, cerrado); un tramo pertenece al día en que abre; el
  horario de un rango, con sus `spans`, es el contrato que leen Citas y Reservas.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:time-outline`, categoría `people`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` (entra en sus plantillas) |
| `requires` | `[]`: no conoce a nadie del equipo ni lee otras apps |
| Usa de otras apps | nada; de la plataforma, la zona horaria (`timezone.get_current_timezone()`, en la fase 1 `settings.TIME_ZONE`) |
| La usan | Citas y Reservas (las dos la requieren): importan `hours_for_range` y `day_label` de `queries.py` (Reservas, también `get_week`) y re-ejecutan sus consultas vivas con sus avisos; la agenda de Citas sigue en vivo `schedule.hours.for_range`; Reservas online, a través de Citas |
| Pantallas | `/schedule/hours`, `/schedule/special-days` (dos tablas: días especiales y cambios temporales) y `/schedule/settings` |
| Operaciones | 6 consultas (`queries.py`) y 10 acciones (`services.py`), todas con `ai=`; 16 rutas en `/api/schedule/…`; 5 consultas abiertas a las API keys |
| Eventos | 8, `schedule.<entidad>.<hecho>` (`events.py`); no reacciona a ninguno |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial` y `0002_default_week` (planta la semana por defecto; su vuelta atrás solo la quita si sigue sin confirmar) |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18), los tramos como líneas de su día |

Las decisiones de diseño (las reglas sin ORM de `engine.py`, el contrato para Citas, los bloqueos, la zona
horaria, las fechas acotadas a 1900–2200) están en «Para quien lo mantiene» del WORKBOOK; las de la migración,
en la ronda 2026-10-22 (CLOSE-SCHEDULE) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/schedule
pnpm test apps/schedule
pnpm e2e tests/e2e/schedule-flows.spec.ts tests/e2e/schedule-hours.spec.ts tests/e2e/schedule-special-days.spec.ts
```

- `test_engine.py` prueba las reglas sin base de datos (precedencia, medianoche, cambio de hora);
  `test_migrations.py`, la semana por defecto y que nunca pisa una semana tocada; `test_services.py`, las
  carreras (dos días especiales o dos cambios temporales a la vez) con hilos.
- Lo que leen Citas y Reservas se prueba contra Horarios real en
  `apps/appointment/tests/test_integration_schedule.py` y `apps/reservation/tests/test_integration_schedule.py`.
- `schedule-flows.spec.ts` recorre los flujos con pantalla en 390, 834 y 1440.
- El paso «Confirma tu horario» del Inicio (SCHEDULE-F03) se prueba contra `base.setup.status` real en
  `tests/test_integration_home.py`, y en pantalla con `fix-schedule-setup-hooks.spec.ts` en 390, 834 y 1440.

## Qué queda fuera

- El icono de estrella de Días especiales y los campos de fecha y hora en el orden del idioma del Hub de
  [`UI-REQUESTS.md`](UI-REQUESTS.md).
- Calendario de festivos precargado, horario por sede o varias plantillas de horario: «Lo que queda fuera» y
  «Lo que NO hace, a propósito» del WORKBOOK.
