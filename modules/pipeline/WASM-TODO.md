# pipeline — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_pipeline/{models.py,services.py}`. El CRUD plano y las
transiciones simples ya están en SQL declarativo Tier 0:
- `pipeline.stages.add`     → `commands/stage_add.sql`   (INSERT directo de etapa).
- `pipeline.deals.mark_lost` → `commands/deal_mark_lost.sql` (UPDATE con guarda `status='open'` en el WHERE).

Lo que sigue es lógica de batch / transición condicional / agregación que **no** cabe en una
sola sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida (permiso, `hub_id`, FK) y persiste en una transacción. Los importes monetarios se
> tratan como decimales con `quantize(0.01)`. Las marcas de tiempo (`:now`) las inyecta el
> host (capacidad de reloj); el WASM solo decide *qué* sellar.

## 1. `create_pipeline`  (command `pipeline.pipelines.create`)
Origen: `PipelineService.create_pipeline`.
- Validar: `name` no vacío; `stages` lista no vacía. Por cada etapa: `code` y `name` obligatorios
  (si falta alguno → error `missing_stage_code` / `missing_stage_name`, índice incluido).
- **Atómico**: la cabecera del pipeline y todas sus etapas se insertan en una sola transacción
  (si una etapa falla, nada se aplica).
- Insertar cabecera `pipeline_pipeline` con `is_active=1`.
- Por cada etapa (índice `i`): emitir intención de insert en `pipeline_stage` con
  `order = stage.order ?? i` (si no se da `order`, se infiere de la posición en la lista),
  `probability_default = stage.probability_default ?? 50`, `is_won`/`is_lost`/`color` por defecto.
- Devolver `{id, name, stages_count, stage_ids:[...]}`.
- Emite `pipeline.pipeline.created`.

## 2. `create_deal`  (command `pipeline.deals.create`)
Origen: `PipelineService.create_deal`.
- Validar: `deal_name` no vacío.
- El runtime lee el pipeline (`pipeline_id`) y la etapa (`stage_id`) y verifica que existen,
  pertenecen al hub y que **la etapa pertenece al pipeline** (`stage.pipeline_id == pipeline.id`,
  si no → error `stage_pipeline_mismatch`).
- Parsear `deal_value` a decimal (error `invalid_amount` si no parsea) y `expected_close_date`
  ISO `YYYY-MM-DD` o NULL (error `invalid_date`).
- **Auto-cierre según la etapa destino** (lógica clave que NO va en SQL):
  - `stage.is_won`  → `status='won'`,  `won_at = now`,  `lost_at = NULL`.
  - `stage.is_lost` → `status='lost'`, `lost_at = now`, `won_at = NULL`.
  - en otro caso    → `status='open'`.
- Siempre sellar `entered_stage_at = now`.
- Insertar el deal y devolver `{id, deal_name, pipeline_id, stage_id, status, deal_value}`.
- Emite `pipeline.deal.created`.

## 3. `move_deal`  (command `pipeline.deals.move`)
Origen: `PipelineService.move_deal`. Es el corazón de la máquina de estados — transición con
guardas que dependen de los flags de la etapa destino, imposible en una sola UPDATE.
- El runtime lee el deal (`deal_id`) y la nueva etapa (`new_stage_id`); verifica que existen y
  son del hub, y que **la nueva etapa pertenece al pipeline del deal** (`new_stage.pipeline_id ==
  deal.pipeline_id`, si no → error `stage_pipeline_mismatch`).
- **Guarda de re-apertura**: si el deal NO está `open` y la etapa destino NO es won/lost →
  error `invalid_state` ("no se puede mover un deal cerrado de vuelta a una etapa abierta").
- Aplicar transición:
  - `new_stage.is_won`  → `status='won'`,  `won_at = now`,  `lost_at = NULL`, `lost_reason = ''`.
  - `new_stage.is_lost` → `status='lost'`, `lost_at = now`, `won_at = NULL`.
  - normal              → `status='open'`, `won_at = NULL`, `lost_at = NULL`, `lost_reason = ''`
    (re-apertura permitida solo porque la guarda anterior ya lo autorizó).
- Siempre: `stage_id = new_stage.id`, `entered_stage_at = now`.
- Devolver `{id, stage_id, status, entered_stage_at}`.
- Emite `pipeline.deal.moved`.

## 4. `pipeline_metrics`  (command read-only `pipeline.pipelines.metrics`)
Origen: `PipelineService.get_pipeline_metrics`. Agregación multi-fila + ratios → no es un
SELECT plano (se expone como handler WASM read-only con permiso `pipeline.view_pipe`; el WASM
recibe las filas de etapas y deals leídas por el runtime y solo calcula).
- El runtime verifica que el pipeline existe/es del hub y lee sus etapas (ordenadas) y **todos**
  sus deals.
- Agrupar deals por `stage_id`. Por etapa calcular:
  `open_count`, `won_count`, `lost_count` y
  `open_value = Σ deal_value de los open`, `won_value = Σ deal_value de los won`
  (decimales, `quantize(0.01)`).
- `totals`: agregados `open_count/won_count/lost_count` y `open_value/won_value`.
- `conversion_rates`: por etapa, `rate = open_count / (open_count + lost_count)` si el
  denominador > 0, si no `0.0`; redondear a 4 decimales. (Ratio de embudo simplificado, tal cual
  el legacy.)
- Devolver `{pipeline_id, stage_metrics:[...], totals:{...}, conversion_rates:[...]}`.
- Read-only: no emite eventos ni persiste nada.
