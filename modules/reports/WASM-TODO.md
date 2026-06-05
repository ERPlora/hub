# reports — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_reports/{models.py,services.py}`. El CRUD plano de definiciones
de informe y las suscripciones ya están en SQL declarativo Tier 0 (`commands/*.sql`). Lo que
sigue es lógica de ejecución / numeración atómica / merge / ciclo de vida que **no** cabe en
una sola sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. La marca de tiempo (`:now`) y la generación de ids
> (`:new_id`) las provee el host; el WASM solo formatea/decide.

## 1. `run_report`  (command `reports.reports.run`, handler `run_report`)
Origen: `ReportService.run_report` + `ReportService._next_run_number`.

Único command con handler WASM. Persiste una fila `reports_run` que representa una ejecución.
El "ejecutor" legacy es un placeholder (no hay query planner): si llega `data` (lista ya
calculada por el caller), `total_rows = len(data)`; si no, `total_rows = 0`. No hay exporter
todavía → `output_location` queda vacío. Pasos:

1. **Cargar el informe**: el runtime lee `reports_report` por `report_id` (+ `hub_id`); si no
   existe o `is_deleted=1` → error `report_not_found`. (El WASM recibe la fila ya leída.)
2. **Validar `output_format`** ∈ {`json`,`csv`,`xlsx`,`pdf`}. (Ya cubierto por el schema, pero
   re-validar defensivamente → error `invalid_output_format`.)
3. **Generar `run_number` atómico** — formato `RPT-YYYYMMDD-NNNN`:
   - `NNNN` = secuencia por `hub_id` + día (4 dígitos, empezando en 0001).
   - El legacy cuenta los runs existentes con prefijo `RPT-{hoy}-` y suma 1 (SELECT→count→+1),
     lo cual **tiene ventana de carrera**. En hub-next debe resolverse como **capacidad de
     counter atómica del runtime** (UPSERT `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`,
     portable SQLite/Postgres) invocada por el handler; el WASM solo formatea
     `RPT-{day}-{n:04d}` con el número devuelto. La unicidad la respalda
     `uq_reports_hub_run_number`.
4. **Merge de filtros** (`filters_applied`): partir de `report.filters` (JSON, puede ser NULL→{})
   y sobreescribir con `filters_override` (override gana): `{**base, **override}`. Si ambos
   vacíos → NULL. El WASM compone el JSON resultante; el runtime lo persiste como TEXT.
5. **Ciclo de vida del run** (el legacy lo hace en dos flushes dentro de una transacción):
   - Insertar `reports_run` con `started_at = :now`, `status='running'`, `output_format`,
     `output_location=''`, `filters_applied` (paso 4), `run_by_ref` (validar uuid o NULL),
     `total_rows=0`.
   - Calcular `total_rows = len(data) if data else 0`.
   - Actualizar la misma fila: `status='completed'`, `completed_at = :now`, `total_rows`.
   - Como es atómico y de un solo run, el handler puede devolver una única intención de INSERT
     ya con `status='completed'`, `started_at=:now`, `completed_at=:now` y `total_rows` calculado
     (no hace falta el doble flush; se conserva la semántica). Si en el futuro la ejecución es
     asíncrona/larga, separar en INSERT(running) + UPDATE(completed/failed).
6. **Validar `run_by_ref`**: si llega, debe ser un uuid válido → si no, error `invalid_run_by_ref`.
7. **Emitir** `reports.run.completed` con `{id, run_number, report_id, status, total_rows, output_format}`.

Notas de futuro (NO implementar ahora, documentado para no perder el contrato):
- El **query planner / DataSourceRegistry** real (que materializa filas desde `data_source`)
  vive fuera del módulo. Cuando exista, `run_report` invocará esa capacidad y `output_location`
  apuntará al artefacto (S3/disco) generado por el **export pipeline** (csv/xlsx/pdf).
- `status='failed'` se reserva para cuando el ejecutor real pueda fallar; el placeholder
  siempre completa.

## 2. Borrado en cascada de un informe  (command `reports.reports.delete`)
Origen: `ReportService.delete_report` (legacy: `cascade="all, delete-orphan"` sobre runs + subs).

El `commands/report_delete.sql` solo hace soft-delete de la cabecera `reports_report`. Para
preservar la semántica de cascada del legacy, el **runtime** debe soft-deletear también las
filas hijas del mismo informe (`reports_run` y `reports_subscription` con `report_id` = el
informe borrado, mismo `hub_id`). Opciones:
- Resolverlo como **command multi-sentencia** (añadir dos UPDATE de soft-delete al array `sql`
  del command, parametrizados por `:report_id`/`:hub_id`/`:now`/`:current_user_id`), **o**
- Un handler WASM que devuelva las tres intenciones de UPDATE (cabecera + N runs + N subs).
Pendiente de decisión del runtime (preferible la vía multi-sentencia SQL si el dispatcher la
soporta — no es lógica de cálculo). Mientras tanto, el delete actual deja runs/subs huérfanos
marcados activos: aceptable porque las queries siempre filtran por `is_deleted=0` del propio
informe vía la UI, pero **no** equivale a la cascada legacy.

## 3. Suscripciones recurrentes — disparo de entregas (tarea programada, futuro)
Origen: campos `frequency` / `delivery_method` / `last_sent_at` de `ReportSubscription` +
`SCHEDULED_TASKS` (vacío en legacy).

El legacy define el modelo de suscripción pero **no** implementa el job que recorre las
suscripciones activas, ejecuta el informe y entrega (email/webhook) actualizando `last_sent_at`.
Cuando se implemente:
- Seleccionar `reports_subscription` activas (`is_active=1`, `is_deleted=0`) cuya cadencia
  (`frequency`) toque según `last_sent_at` vs `:now`.
- Por cada una: invocar `run_report`, entregar por `delivery_method` (capacidad host Tier 1:
  email / `http.fetch` para webhook), y actualizar `last_sent_at = :now`.
- Operación batch sobre N filas con efectos externos → handler WASM que devuelve intenciones +
  capacidades de host. No bloqueante para esta migración.
