# opportunities — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_opportunities/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`):
`update_stage`, `mark_lost`, `update_value_probability`, `complete_activity`. Lo que sigue
es lógica de numeración atómica, cálculo condicional y composición de texto que **no** cabe
en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos internos
> `_insert_opportunity` / `_insert_activity` a ejecutar) que el runtime valida y persiste en
> una transacción. Todos los importes son decimales con `quantize(0.01)`.

## Tabla de etapas → probabilidad por defecto
Origen: `STAGE_DEFAULT_PROBABILITY` (services.py). Constante compartida por varios handlers:
`prospecting=10, qualification=25, proposal=50, negotiation=75, won=100, lost=0`.
Etapas válidas: `prospecting, qualification, proposal, negotiation, won, lost`.

---

## 1. `create_opportunity`  (command `opportunities.opportunities.create`)
Origen: `OpportunityService.create_opportunity` + `generate_opp_number`.
- Validar: `customer_name` no vacío (también lo cubre el schema); `stage` válido.
- Parsear/validar `value` como Decimal ≥ 0 (error `invalid_value`).
- Parsear `expected_close_date` (ISO `YYYY-MM-DD` o vacío/None → NULL; error `invalid_date`).
- Parsear `assigned_to` como UUID si viene no vacío (error `invalid_assigned_to`) → `assigned_to_ref`.
- Resolver `probability`:
  - si el cliente la envía → validar 0..100 (error `invalid_probability`);
  - si no → `STAGE_DEFAULT_PROBABILITY[stage]`.
- Generar `opp_number` atómico → ver pieza 5 (counter). Formato `OPP-YYYYMMDD-NNNN`.
- Emitir intención `_insert_opportunity` con binds: `new_id, opp_number, customer_name,
  customer_email, value, probability, expected_close_date, stage, assigned_to_ref, notes`.
- Devolver `{id, opp_number, customer_name, value, probability, stage}`.

## 2. `mark_won`  (command `opportunities.opportunities.mark_won`)
Origen: `OpportunityService.mark_won`.
- Leer la oportunidad (scope hub). Guardas:
  - `stage == 'won'` → error `already_won`;
  - `stage == 'lost'` → error `already_lost` ("Cannot win a lost opportunity").
- Mutación: `stage='won'`, `probability=100`.
- **Append condicional de notes** (no cabe en SQL plano): si llega `notes` no vacío,
  componer `trail = "[WON] {notes}"` y `new_notes = (opp.notes + "\n" + trail).strip()` si ya
  había notes, si no `trail`. Emitir intención UPDATE de la cabecera con `stage/probability/notes`.
- Devolver `{id, opp_number, stage, value, weighted_value}` (weighted = pieza 4).
- Nota: `mark_lost` SÍ cabe en SQL (`commands/mark_lost.sql`) porque sobreescribe `close_reason`
  directamente sin componer texto; queda como Tier 0.

## 3. `log_activity`  (command `opportunities.activities.log`)
Origen: `OpportunityService.log_activity`.
- Validar `activity_type ∈ {call,email,meeting,note}` (también schema) y que la oportunidad existe.
- Parsear `scheduled_for`: acepta `YYYY-MM-DD` o ISO datetime completo; vacío/None → NULL
  (error `invalid_datetime`).
- **Lógica condicional de completado**: si `scheduled_for` es NULL ⇒ la actividad es un registro
  de algo ya ocurrido → `completed_at = now`; si hay `scheduled_for` ⇒ `completed_at = NULL`
  (queda pendiente). `completed_by_ref = current_user` cuando se completa en el momento.
- Emitir intención `_insert_activity` con binds: `new_id, opportunity_id, activity_type,
  description, scheduled_for, completed_at, completed_by_ref`.
- Devolver `{id, opportunity_id, activity_type, scheduled_for, completed_at}`.

## 4. Cálculo de `weighted_value`
Origen: `Opportunity.weighted_value` (models.py).
- `weighted_value = quantize(value * probability / 100, 0.01)`.
- Lo usa la UI (lo calcula inline el Web Component a partir de `value`/`probability`) y los
  handlers que devuelven `weighted_value` en su respuesta (`mark_won`). No se persiste columna.

## 5. Contador atómico de nº de oportunidad (`generate_opp_number`)
Origen: `OpportunityCounter` + `generate_opp_number` (UPSERT `INSERT ... ON CONFLICT DO UPDATE
... RETURNING`). Formato `OPP-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres.
- En hub-next se resuelve como **capacidad del runtime** (counter UPSERT sobre
  `opportunities_counter`, único por `(hub_id, day)`) invocada por el handler; el WASM solo
  formatea `OPP-{day}-{n:04d}` con el número devuelto.
- El índice único `ix_opp_hub_number` sobre `(hub_id, opp_number)` es la guarda adicional.

## 6. `get_pipeline_summary` — zero-fill (Tier 0/UI, no bloqueante)
Origen: `OpportunityService.get_pipeline_summary`.
- La query `pipeline_summary.sql` ya agrega `count` y `total_value` por etapa (solo las que
  tienen filas). El **zero-fill** de las etapas sin oportunidades y los totales `total_count`/
  `total_value` agregados los compone la UI/SDK iterando `OPPORTUNITY_STAGES`. No requiere WASM.

## 7. Guardas de `update_stage` ya en SQL — nota sobre el bump de probabilidad
Origen: `OpportunityService.update_stage`.
- El rechazo de `won`/`lost` (deben ir por `mark_won`/`mark_lost`) lo cubre el enum del schema
  `update_stage.json`; el rechazo de oportunidades ya cerradas lo cubre la cláusula
  `WHERE stage NOT IN ('won','lost')` de `update_stage.sql`.
- Lo que NO cabe en SQL plano es el **bump de probabilidad al default de la nueva etapa solo si
  la actual es menor** (`if opp.probability < default_prob: opp.probability = default_prob`).
  Si se quiere conservar ese comportamiento, moverlo a un handler WASM que lea la probabilidad
  vigente y devuelva el UPDATE con el `max(actual, default_etapa)`. Hoy `update_stage.sql` solo
  mueve la etapa (comportamiento conservador y seguro); no bloqueante.
