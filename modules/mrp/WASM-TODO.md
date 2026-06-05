# mrp — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_mrp/{models.py,services.py}`. El CRUD de runs/requirements y
las transiciones de estado simples de las sugerencias (`approve`/`reject`) ya están en SQL
declarativo Tier 0 (`commands/suggestion_approve.sql`, `commands/suggestion_reject.sql`) y
las lecturas en `queries/*.sql`. Lo que sigue es la lógica de **cálculo / agregación / batch**
que NO cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos que el runtime le
> pase, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime valida y
> persiste en una transacción. Todas las cantidades son decimales con `quantize(0.001)`
> (Numeric(15,3) en el modelo legacy).

---

## 1. `create_run` — el motor de netting  (command `mrp.runs.create`)
Origen: `MRPService.create_run` (+ `MRPService._next_run_number`). Es el corazón del módulo.
Validación de payload por `schemas/run_create.json`; el resto de reglas viven aquí.

**Entradas (payload):**
- `horizon_days` (int, default 30) — validar `> 0`, si no → error `invalid_horizon`.
- `demand_inputs`: lista de `{product_ref, quantity, required_date?, source_type, source_ref?, suggested_type?}`.
- `on_hand`, `on_order`, `lead_times`: mapas `product_ref → valor` (faltantes = 0).

**Lógica (no-CRUD):**
1. **Generar `run_number`** atómico con formato `MRP-YYYYMMDD-NNNN` (secuencia por hub+día,
   4 dígitos). En legacy es un `SELECT COUNT(...) LIKE prefix% + 1` (ventana de carrera).
   En hub-next debe resolverse como **capacidad de contador atómico del runtime** (UPSERT
   `RETURNING`, sin ventana SELECT→UPDATE) — igual que `quotes` pieza 5. El WASM solo formatea
   `MRP-{day}-{n:04d}` con el número que devuelve el runtime.
2. **Crear la cabecera `mrp_run`** con `status='running'`, `started_at=now`, `run_date=hoy`,
   `parameters` = JSON `{horizon_days, demand_count, on_hand_count, on_order_count, lead_times_count}`.
   → intención de insert sobre `mrp_run`.
3. **Agregar demanda por `product_ref`** (bucketing):
   - Validar cada entry: dict, `product_ref` no vacío (`missing_product`), `quantity` parseable a
     Decimal (`invalid_quantity`), `required_date` ISO o vacío (`invalid_date`),
     `source_type ∈ {mo, sales_order, forecast}` (`invalid_source`),
     `suggested_type ∈ {buy, make}` (`invalid_type`).
   - Sumar `quantity` por producto. Conservar el **`required_date` más temprano** entre entries.
   - `suggested_type`: si **cualquier** contribuyente dice `make`, el bucket pasa a `make`
     (un make subsume un buy).
4. **Por cada bucket** computar el neto:
   - `qty_required = quantize(Σ quantity, 0.001)`.
   - `qty_on_hand  = quantize(on_hand[product_ref] | 0, 0.001)`.
   - `qty_on_order = quantize(on_order[product_ref] | 0, 0.001)`.
   - `net = max(0, qty_required - qty_on_hand - qty_on_order)` (quantize 0.001).
   - → intención de insert sobre `mrp_requirement` (una fila por producto, **siempre**, net≥0).
5. **Si `net > 0`** emitir además una sugerencia:
   - `lead = max(0, int(lead_times[product_ref] | 0))`.
   - `suggested_date = required_date - lead días` (si hay `required_date` y `lead`).
   - → intención de insert sobre `mrp_suggestion` con `suggested_type` del bucket,
     `quantity=net`, `status='pending'`, `related_requirement_id` = id de la requirement creada.
6. **Cerrar el run**: `status='completed'`, `completed_at=now`,
   `total_requirements=N_reqs`, `total_suggestions=N_sugs` → intención de update sobre `mrp_run`.
   Si algo falla durante el cómputo: `status='failed'`, `completed_at=now`, error `run_failed`
   (la transacción del runtime debe revertir reqs/sugs parciales y dejar solo la cabecera failed,
   o revertir todo — decisión del runtime; el legacy persistía la cabecera failed).
7. **Devolver** `{id, run_number, status, total_requirements, total_suggestions}` y emitir el
   evento `mrp.run.completed`.

**Binds que el runtime debe inyectar al handler:** `hub_id`, `current_user_id`, `now`,
y el siguiente nº de secuencia del contador `mrp_run` por hub+día.

---

## 2. Rastro textual en `notes` de las sugerencias (Tier 1, no crítico)
Origen: `MRPService.approve_suggestion(notes=...)` y `reject_suggestion(reason=...)`.
- El SQL Tier 0 actual (`suggestion_approve.sql`/`suggestion_reject.sql`) hace la transición de
  estado y, en reject, escribe `notes = :reason` (plano).
- El legacy **anexa con marca**: `"{notes}\n[APPROVED] {notes}"` y `"{notes}\n[REJECTED] {reason}"`.
  En approve, además, las notas opcionales solo se anexan si se pasan.
- Para conservar ese audit-trail (append preservando lo previo), moverlo a un handler WASM que
  lea el `notes` actual (provisto por el runtime) y componga el nuevo texto. No bloqueante:
  la versión SQL plana es funcionalmente suficiente para el MVP.

---

## 3. Guarda de estado en approve/reject (ya cubierta en SQL, documentada aquí)
Origen: `approve_suggestion`/`reject_suggestion` rechazan si `status != 'pending'`
(error `invalid_state`).
- El SQL Tier 0 lo expresa con `AND status = 'pending'` en el WHERE: si la fila no está pending
  no se actualiza ninguna fila. El **runtime debe traducir "0 filas afectadas" → error
  `invalid_state`** (no un éxito silencioso). Si se prefiere un mensaje de error explícito por
  estado actual, subir esta guarda al handler WASM (leer estado, validar, devolver intención).
