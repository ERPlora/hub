# ai_reports — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_ai_reports/{models.py,services.py}`. El CRUD plano de plantillas
(`create_template`, `update_template`) y los listados ya están en SQL declarativo Tier 0
(`commands/template_*.sql`, `queries/*.sql`). Lo que sigue es lógica de ciclo de vida /
contador atómico / validación que **no** cabe en una sola sentencia SQL y debe convertirse en
handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, valida/calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. Los importes (`cost_eur`) son decimales con
> `quantize(0.000001)` (Numeric(12,6)); los `tokens_used` son enteros.

## 1. `create_request`  (command `ai_reports.requests.create`)
Origen: `AIReportService.create_request` + `generate_request_number`.
- Validar: `user_query` no vacío (tras `strip()`) → si vacío, error `missing_user_query`.
- Si llega `template_id` (no null): el runtime debe verificar que la plantilla existe y
  pertenece al hub (FK blando). Si no existe → error `template_not_found`.
- Generar `request_number` atómico → ver pieza 4 (counter). Formato `AIR-YYYYMMDD-NNNN`.
- `data_context` llega como JSON string (default `"{}"`).
- Insertar la fila de petición con `status='queued'`, `data_context` normalizado,
  `tokens_used=0`, `cost_eur=0`, timestamps de auditoría del runtime.
- Devolver `{id, request_number, status}` y emitir `ai_reports.request.created`.

## 2. `run_request`  (command `ai_reports.requests.run`)
Origen: `AIReportService.run_request`. Es un placeholder del registro del resultado LLM:
el caller pasa la respuesta ya recibida + las cifras de contabilidad (la llamada al LLM real
NO la hace este módulo — va por el proxy de Cloud, §9.3).
- **Guarda de estado**: solo si `status IN ('queued','running')`; si no → error `invalid_state`
  (con el status actual en el mensaje).
- Validar `tokens_used`: entero `>= 0` → si no, error `invalid_tokens`.
- Validar/parsear `cost_eur`: decimal válido (string) → si no, error `invalid_cost`.
- Transición `queued/running → completed` en una sola llamada:
  - `status='completed'`, `llm_response=<payload>`, `tokens_used`, `cost_eur`.
  - `prompt_used` solo se sobrescribe si llega no vacío.
  - `started_at = now` si era NULL; `completed_at = now`.
- Devolver `{id, request_number, status, tokens_used, cost_eur}` y emitir
  `ai_reports.request.completed`.

## 3. `cancel_request`  (command `ai_reports.requests.cancel`)
Origen: `AIReportService.cancel_request`.
- **Guarda de estado**:
  - `status IN ('completed','failed')` → error `terminal_state` (no cancelable; re-encolar otra).
  - `status == 'cancelled'` → error `already_cancelled`.
- Transición a `status='cancelled'`, `completed_at = now`.
- Si llega `reason` no vacío: **append** a `error_message` con prefijo `[CANCELLED] {reason}`
  (componer el nuevo texto a partir del actual — capacidad de "reloj"/concatenación del host;
  el WASM recibe el `error_message` actual leído por el runtime).
- Devolver `{id, request_number, status}` y emitir `ai_reports.request.cancelled`.

## 4. Contador atómico de nº de petición (`generate_request_number`)
Origen: `AIReportCounter` + `generate_request_number` (UPSERT `INSERT ... ON CONFLICT DO UPDATE
... RETURNING` sobre `(hub_id, day)`). Formato `AIR-YYYYMMDD-NNNN` (NNNN = secuencia por
hub+día, 4 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres.
- En hub-next se resuelve como capacidad del runtime (counter UPSERT sobre `ai_reports_counter`)
  invocada por el handler; el WASM solo formatea `AIR-{day}-{n:04d}` con el número devuelto.

## 5. Agregación de estadísticas (`get_request_stats`) — Tier 1, no crítico
Origen: `AIReportService.get_request_stats`.
- La query `ai_reports.requests.stats` (`queries/request_stats.sql`) ya devuelve, por estado:
  `{status, count, tokens, cost_eur}` para `created_at >= :since_iso` (el caller calcula
  `since_iso = now - period_days`).
- La forma final del legacy — `{period_days, total, by_status:{...}, total_tokens,
  total_cost_eur}` con `total_cost_eur` redondeado a `quantize(0.000001)` — la compone el
  SDK/UI sumando las filas, o un handler WASM si se quiere devolver el shape exacto en un
  solo round-trip. No bloqueante; la suma sobre N filas no necesita BD.

## Notas de portabilidad
- `default_data_sources` y `data_context` se almacenan como JSON string (TEXT) — el runtime
  no los interpreta; el WASM/UI los (de)serializa.
- `template_id` es FK blando `ON DELETE SET NULL` — borrar una plantilla NO borra peticiones.
- No hay tareas programadas en el legacy (`SCHEDULED_TASKS = []`); no se declara ninguna.
