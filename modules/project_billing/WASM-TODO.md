# project_billing — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_project_billing/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`). Lo que
sigue es lógica de autonumeración, batch (rollup) y atomicidad que **no** cabe en una sola
sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el runtime,
> calcula y devuelve *intenciones* (comandos privados `_insert_invoice` / `_set_milestone_status`
> / `_mark_time_invoiced` a ejecutar, más la fila a insertar) que el runtime valida y persiste en
> una transacción. Todos los importes son decimales con `quantize(0.01)`.

Comandos con `handler.type=wasm` en `module.json`:
`project_billing.contracts.create` → `create_contract`,
`project_billing.invoices.generate` → `generate_invoice`,
`project_billing.invoices.mark_paid` → `mark_invoice_paid`.

---

## 1. `create_contract`  (command `project_billing.contracts.create`)
Origen: `ProjectBillingService.create_contract` + `_generate_contract_number`.
- Validar: `customer_name` no vacío (`missing_customer`); `billing_type` ∈
  `{fixed_price, time_and_material, milestone, retainer}` (`invalid_billing_type`).
  (El JSON Schema ya cubre estos dos; el WASM los reafirma defensivamente.)
- Parsear/validar `start_date` / `end_date` (ISO `YYYY-MM-DD` o vacío → NULL) → `invalid_date`.
- Parsear `total_amount` / `hourly_rate` como Decimal (vacío → 0) → `invalid_amount`.
- Generar `contract_number` atómico → ver pieza 4 (counter). Formato `PBC-YYYYMMDD-NNNN`.
- Insertar la cabecera con `status='draft'` (intención: fila para `project_billing_contract`;
  el runtime puede exponer un `_insert_contract` o el WASM devolver la fila directa de la tabla
  propia — al ser la tabla del propio módulo, se permite vía intención validada por el runtime).
- Devolver `{id, contract_number, project_ref, customer_name, billing_type, status}`.

## 2. `generate_invoice`  (command `project_billing.invoices.generate`)  ← núcleo del módulo
Origen: `ProjectBillingService.generate_invoice`.
- Guarda: `include_milestones || include_time` (si ambos false → `nothing_to_invoice`).
- Parsear `due_in_days` (int, default 30) → `invalid_due`.
- Datos que el runtime debe leer y pasar al WASM (NO los lee el WASM):
  - hitos del contrato con `status='pending'` (query `project_billing.milestones.list`,
    filtro `status='pending'`), si `include_milestones`.
  - partes de horas del contrato con `is_invoiced=0` (query `project_billing.time_entries.list`,
    `only_unbilled=1`), si `include_time`.
- Si no hay ni hitos pendientes ni horas sin facturar → `nothing_to_invoice`.
- Construir `line_items` (snapshot JSON) y `total`:
  - Por cada hito: `{type:"milestone", id, name, due_date, amount: quantize(amount,0.01)}`;
    `total += amount`.
  - Por cada parte: `line_total = quantize(hours * hourly_rate, 0.01)`;
    `{type:"time_entry", id, entry_date, hours, hourly_rate, employee_ref, description,
     amount: line_total}`; `total += line_total`.
- Generar `invoice_number` atómico → pieza 4. Formato `PIV-YYYYMMDD-NNNN`.
- `invoice_date = hoy`; `due_date = hoy + due_in_days`.
- Emitir intenciones (todas dentro de UNA transacción del runtime):
  1. `_insert_invoice` con `{contract_id, invoice_number, invoice_date, due_date,
     amount: quantize(total,0.01), line_items: <json>}` (status='draft' lo fija el SQL).
  2. por cada hito incluido: `_set_milestone_status` con `{milestone_id, status:'invoiced',
     invoiced_at: now, paid_at: NULL}`.
  3. por cada parte incluido: `_mark_time_invoiced` con `{time_entry_id}`.
- Devolver `{id, invoice_number, contract_id, amount, status:'draft',
  milestone_count, time_entry_count, line_count}`.
- **Por qué WASM y no SQL**: agrega N filas heterogéneas (hitos + partes) en un snapshot JSON,
  calcula `line_total` por línea, suma el total y muta N filas de dos tablas + inserta una
  tercera, todo atómico. Imposible en una sola sentencia.

## 3. `mark_invoice_paid`  (command `project_billing.invoices.mark_paid`)
Origen: `ProjectBillingService.mark_invoice_paid`.
- Guarda de estado: solo desde `draft` o `sent` (si no → `invalid_state`). El runtime lee la
  factura (`project_billing.invoices.get`) y pasa `status` + `line_items` al WASM.
- Parsear el snapshot JSON `line_items`: recolectar los `id` de los items con `type=="milestone"`
  (ignorar ids inválidos, como el legacy con `try/except`).
- Emitir intenciones (UNA transacción):
  1. transición de la factura → `paid` (intención de update sobre la tabla propia, o un
     `_set_invoice_status` si se añade; de momento el WASM puede usar `_insert_invoice`-style
     update sobre `project_billing_invoice`).
  2. por cada `milestone_id` cuyo estado actual ≠ `paid`: `_set_milestone_status` con
     `{milestone_id, status:'paid', invoiced_at: <conservar>, paid_at: now}`.
     (El runtime debe pasar el `invoiced_at` actual de cada hito para no perderlo, o el
     `_set_milestone_status` debe aceptar dejar `invoiced_at` intacto — ver nota de contrato.)
- Las horas ya llevan `is_invoiced=1` desde la generación; no tienen flag "paid" adicional.
- Devolver `{id, invoice_number, status:'paid', milestones_marked_paid: N}`.
- **Por qué WASM**: parsea JSON, hace N updates condicionales sobre hitos según el contenido del
  snapshot, y debe ser atómico con la transición de la factura.

> NOTA de contrato sobre `_set_milestone_status`: el SQL helper actual escribe SIEMPRE
> `invoiced_at` y `paid_at` con lo que reciba. Para `mark_invoice_paid` el WASM debe reenviar el
> `invoiced_at` previo del hito (leído por el runtime) para conservarlo. Alternativa más limpia:
> partir el helper en `_set_milestone_invoiced` / `_set_milestone_paid` cuando se implemente el
> handler; por ahora un único helper parametrizado mantiene el contrato mínimo.

## 4. Contadores atómicos de número (`PBC-…` y `PIV-…`)
Origen: `_generate_contract_number` / `_generate_invoice_number` (legacy: `COUNT(*) + 1` por
prefijo de día — NO atómico, condición de carrera bajo concurrencia).
- Formato: `PBC-YYYYMMDD-NNNN` (contratos) y `PIV-YYYYMMDD-NNNN` (facturas); `NNNN` = secuencia
  por hub+día, 4 dígitos.
- En hub-next debe ser **atómico** (sin ventana SELECT→COUNT→INSERT) en SQLite y Postgres. Se
  resuelve como **capacidad del runtime** (counter UPSERT `INSERT ... ON CONFLICT DO UPDATE ...
  RETURNING`, namespaced por `{hub_id, serie='PBC'|'PIV', day}`) invocada por el handler; el WASM
  solo formatea `PBC-{day}-{n:04d}` / `PIV-{day}-{n:04d}` con el número devuelto.

## 5. Default de tarifa horaria en `log_time` (Tier 1, opcional)
Origen: `ProjectBillingService.log_time` — si `hourly_rate` viene vacío, hereda
`contract.hourly_rate`; y guarda `hours > 0` (`invalid_hours`), `entry_date` default = hoy.
- Hoy `commands/time_log.sql` persiste los valores ya resueltos y delega el default + la guarda
  al SDK/UI. Si se quiere reforzar server-side (recomendado para clientes API que no usan la UI),
  convertir `project_billing.time_entries.log` en handler WASM `log_time`:
  - leer el contrato (runtime → `project_billing.contracts.get`) para tomar su `hourly_rate`;
  - si payload `hourly_rate` vacío/null → usar el del contrato;
  - validar `hours > 0`; `entry_date` vacío → hoy;
  - emitir la inserción. No bloqueante para el MVP.

## 6. `get_unbilled_amount`  (query auxiliar legacy — Tier 1, opcional)
Origen: `ProjectBillingService.get_unbilled_amount`. Suma de hitos `pending` + `line_total` de
horas no facturadas para un contrato. No se migró como query SQL porque agrega dos tablas con un
cálculo (`hours*rate`) por fila. Si se necesita como número de cabecera en la UI, calcularlo en
el cliente a partir de `milestones.list(status='pending')` + `time_entries.list(only_unbilled=1)`,
o exponerlo como función WASM de solo-lectura que el runtime alimente con esas dos listas. No
bloqueante.
