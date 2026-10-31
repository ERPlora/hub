# Control horario (`attendance`)

El registro de jornada del negocio (art. 34.9 ET): cada persona ficha la entrada y la salida con un toque, con
sus pausas en medio; el responsable ve al equipo y quién está dentro ahora, corrige una jornada con un motivo
que queda en su historial y saca el mes en CSV. Ninguna jornada se borra y se conservan cuatro años.

- **Estado**: completa (2026-10-31): los 13 flujos, `ATTENDANCE-F01` … `F13`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Fichar** (F01, F02): entrada, salida y pausas con la hora del servidor; una sola jornada abierta y una sola
  pausa en curso (índices únicos parciales y bloqueo de la ficha de Personal); una jornada que cruza la
  medianoche cuenta en el día del negocio en que empezó.
- **Ubicación** (F03, F04): con «Pedir la ubicación…» activado, un dispositivo **personal** (el modo que un
  administrador eligió en él, BASE-F62; lo lee `services.device_source` de la cookie `hub_device`) tiene que
  estar dentro del radio del local para fichar la entrada; la distancia la mide el Hub (`geopy`). El TPV
  compartido, un navegador desconocido, la API sin navegador y fichar a otra persona (F12) nunca la piden. La
  salida nunca se bloquea. Las coordenadas exactas solo se guardan si se pidieron.
- **Revisión** (F05): una jornada abierta más horas de las de Ajustes sale «Por revisar», sin tiempo trabajado;
  la marca la tarea `review_stale` del worker (cada 15 minutos) y también la siguiente entrada de esa persona.
- **Registros** (F06, F07, F09–F11): las mías o las de todo el equipo, con filtros, «Historial» de correcciones,
  «Fichados ahora» encima de la tabla y en el panel del Inicio, y el CSV del filtro entero.
- **Correcciones** (F08, F13): con motivo obligatorio, sin solapes y con rastro que no se borra; la baja de una
  persona en Personal cierra su jornada abierta por el relay del outbox.
- **Fichar a otros** (F12): el responsable, por el asistente o la API, por nombre o por id.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:log-in-outline`, categoría `people`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` |
| `requires` | `["staff"]`: la jornada es de una ficha de Personal (`staff.Member`) |
| Usa de otras apps | Personal (fichas y nombres, también las dadas de baja); de la plataforma, la persona de la sesión (`base.HubUser`) y el modo del dispositivo (`base.queries.device_of`, BASE-F62); la pantalla Fichar sigue `base.device.current` |
| La usan | ninguna app la requiere hoy; el Inicio pinta su panel «Fichados ahora» |
| Pantallas | `/attendance/clock`, `/attendance/records` y `/attendance/settings` |
| Operaciones | 10 consultas (`queries.py`) y 8 acciones (`services.py`), todas con `ai=`; 16 rutas en `/api/attendance/…`; 16 operaciones abiertas a las API keys |
| Eventos | 7, `attendance.<entidad>.<hecho>` (`events.py`); reacciona a `staff.member.terminated` |
| Tareas programadas | `attendance.record.review_stale`, `*/15 * * * *` |
| Migraciones | `0001_initial`, `0002_correction_author` y `0003_hub_users` (expand de la BD por negocio) |
| Admin | Django admin en `hubs.erplora.com`: ajustes con CRUD; jornadas, pausas y correcciones en solo lectura (salvo la nota interna), porque una hora solo cambia con una corrección con rastro |

## Tests

- `uv run pytest -q apps/attendance` (servicios, consultas, vivos con dos negocios, concurrencia con hilos, relay
  real del worker, integración con Personal, asistente e Inicio).
- `pnpm exec vitest run apps/attendance/frontend`.
- e2e: `tests/e2e/attendance-flows.spec.ts`, `attendance-device-location.spec.ts` (F03 con un dispositivo
  compartido y otro personal), `attendance-clock.spec.ts`, `attendance-settings-location.spec.ts`,
  `attendance-assistant.spec.ts` y `fix-attendance-setup-hooks.spec.ts`, en 390, 834 y 1440.
