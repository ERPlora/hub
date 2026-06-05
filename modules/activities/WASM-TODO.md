# activities — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_activities/services.py`. El CRUD plano (alta de actividad,
reasignación, alta de recordatorio) y las lecturas con filtros ya están en SQL declarativo
Tier 0 (`commands/*.sql`, `queries/*.sql`). Lo que sigue es lógica de **transición de estado
con guardas** y **agregación/estadística** que requiere leer estado previo, ramificar y/o
agregar en memoria, y por tanto no cabe en una sola sentencia SQL: va a handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. El runtime lee la(s) fila(s) necesarias y se
> las pasa al WASM en el payload; el WASM valida la guarda, calcula y devuelve *intenciones*
> (UPDATE de cabecera + evento a emitir) que el runtime valida y persiste en transacción.
> El "ahora" (timestamp) lo aporta el host (capacidad reloj), no el WASM.

## 1. `mark_completed`  (command `activities.activities.complete`)
Origen: `ActivityService.mark_completed`.
- Binds que el runtime pasa al WASM: la actividad actual (`id`, `hub_id`, `status`) + el
  payload (`activity_id`, `duration_minutes?`) + `:now` (host clock) + `:current_user_id`.
- **Guarda de estado**: solo se completa si `status == 'pending'`. Si no → error
  `invalid_state` ("Only pending activities can be completed").
- Intención de UPDATE: `status='completed'`, `completed_at=:now`,
  `duration_minutes = coalesce(payload.duration_minutes, duration_minutes)`,
  `updated_by=:current_user_id`, `updated_at=:now`.
- Emite `activities.activity.completed` con `{id, status, completed_at, duration_minutes}`.
- No expresable en un solo UPDATE porque la guarda depende del status leído y la respuesta
  debe distinguir error vs éxito (no basta `WHERE status='pending'` silencioso).

## 2. `cancel_activity`  (command `activities.activities.cancel`)
Origen: `ActivityService.cancel_activity`.
- Binds: actividad actual (`id`, `hub_id`, `status`, `description`) + payload (`activity_id`,
  `reason?`) + `:now` + `:current_user_id`.
- **Guardas de estado**:
  - `status == 'completed'` → error `completed_locked` ("Completed activities cannot be cancelled").
  - `status == 'cancelled'` → error `already_cancelled`.
- Si hay `reason`, **componer** el nuevo `description` (lógica de string no-SQL):
  `marker = "[CANCELLED] " + reason`; nuevo `description = (desc + "\n" + marker).strip()`
  si había descripción, si no `marker`.
- Intención de UPDATE: `status='cancelled'`, `description = <compuesto>`,
  `updated_by=:current_user_id`, `updated_at=:now`.
- Emite `activities.activity.cancelled` con `{id, status}`.

## 3. `get_activity_stats`  (query lógica → command `activities.activities.stats`)
Origen: `ActivityService.get_activity_stats`.
- Binds: lista de actividades del hub creadas desde `:since` (= `:now - period_days`),
  filtradas opcionalmente por `assigned_to`. El runtime ejecuta el SELECT y pasa las filas
  (solo `activity_type`, `status`) al WASM.
- **Validación**: `period_days` entero y > 0 → error `invalid_period` si no.
- **Agregación en memoria**: contar por `activity_type` (`by_type`) y por `status`
  (`by_status`); `total = nº filas`.
- Devuelve `{period_days, total, by_type:{...}, by_status:{...}}`.
- No es un query Tier 0 porque produce dos histogramas (mapas) en una sola respuesta; un
  `GROUP BY` único no da las dos dimensiones a la vez de forma cómoda para el SDK.

## Notas de portabilidad
- `list_pending_today` (legacy) NO va a WASM: se portó como query Tier 0
  (`activities_pending_today.sql`); el cálculo del rango `[inicio_dia, inicio_dia_siguiente)`
  en UTC lo hace el SDK/host y se pasa como binds `:day_start`/`:day_end`.
- El borrado en cascada de recordatorios al borrar una actividad lo cubre la FK
  `ON DELETE CASCADE` + soft-delete del módulo (mismo módulo OWNea ambas tablas).
