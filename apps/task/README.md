# Tareas (`task`)

La lista de cosas por hacer del equipo: tareas con título, prioridad, fecha límite y una persona de Personal
que se encarga, agrupadas en proyectos, partidas en subtareas y con un hilo de comentarios. El empleado ve y
cambia las suyas (asignadas o creadas por él); el responsable, todas.

- **Estado**: completa (2026-10-21): los 15 flujos, `TASK-F01` … `F15`, están `hecho`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Las tareas** (F01–F11): crear con número `TSK-AAAAMMDD-NNNN` sin huecos (el día del negocio), ver y
  buscar con filtros tras el embudo, «Mis tareas» abiertas por vencimiento, la hoja con sus datos, iniciar o
  cambiar el estado (Hecha sella la fecha de completada), completar, asignar a una persona activa de
  Personal, «Asignármela» y desasignar, editar solo lo enviado, subtareas en el proyecto de la madre, un hilo
  de comentarios que no se edita ni se borra, y borrar con sus subtareas y comentarios.
- **Los proyectos** (F12–F14): crear con código único y color `#RRGGBB`, abrir con sus tareas, cambiar
  nombre y color, desactivar o activar, y borrar dejando sus tareas sin proyecto.
- **La baja en Personal** (F15): las tareas abiertas de quien deja el equipo quedan sin asignar, por el relay
  del outbox, una sola vez por baja.
- **Lo propio**: una tarea que el empleado no ve da «no existe» por cualquier puerta (id, número o título), y
  nada de ella se cuela por otra fila ni por los contadores.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:checkbox-outline` (el del módulo viejo), categoría `organization`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` (entra en sus plantillas) |
| `requires` | `["staff"]`: el responsable y el dueño de un proyecto son fichas de Personal (`staff.Member`) |
| Usa de otras apps | Personal: `Member` por clave ajena (`assigned_to`, `owner`), `resolve_member` (con bloqueo de la ficha), `actor_user_id` y `own_member`; las pantallas llaman a `staff.member.list` y `staff.member.mine` |
| La usan | Automatizaciones llama por nombre a `task.task.create` (recetas de Citas y Reservas online, FLOW-F33); Tareas no sabe de ellas |
| Pantallas | `/task/tasks` (Todas / Mis tareas) y `/task/projects`; la hoja de la tarea y la del proyecto, en un `ion-modal` sin URL propia |
| Operaciones | 7 consultas (`queries.py`) y 11 acciones (`services.py`), todas con `ai=`; 17 rutas en `/api/task/…` (`task.task.release_member`, solo de la plataforma, no tiene ruta) |
| Eventos | 10, `task.<entidad>.<hecho>` (`events.py`); `REACTIONS` a `staff.member.terminated` (`task.task.release_member`), por el relay del outbox |
| Tareas programadas | ninguna |
| Migraciones | `0001_initial` |
| Admin | Django admin con CRUD en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (número sin huecos, lo propio, el orden de los bloqueos con Personal, el «hoy» del
negocio) están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la ronda 2026-10-21
(CLOSE-TASK) de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/task
pnpm test apps/task
pnpm e2e tests/e2e/task-flows.spec.ts tests/e2e/task-tasks.spec.ts tests/e2e/task-employee.spec.ts
```

- `tests/test_integration_staff.py` va contra Personal real; `test_relay.py`, la baja en Personal entregada
  por el tick real del relay del outbox, con dos negocios; `test_concurrency.py`, con dos personas a la vez
  en hilos (números consecutivos, completar una vez, el admin del Hub borrando a la vez lo que una escritura nombra).
- `task-flows.spec.ts` recorre los flujos con pantalla en 390, 834 y 1440; `task-employee.spec.ts`, lo que ve
  y cambia el empleado.

## Qué queda fuera

- Avisos y recordatorios, registro de tiempo, tareas programadas, adjuntos, incidencias de clientes y editar
  o borrar comentarios: «Lo que NO hace, a propósito» del WORKBOOK.
- El panel lateral del `DataTable` y el selector de color de [`UI-REQUESTS.md`](UI-REQUESTS.md).
