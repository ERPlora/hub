# supplier_invoices — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_supplier_invoices/{models.py,services.py}`. Las transiciones de
estado simples (validate, mark_paid, cancel) ya están en SQL declarativo Tier 0
(`commands/*.sql`, todas `transaction:true`). Lo que sigue es el **alta de factura**: lógica de
cálculo/batch/atomicidad que **no** cabe en una sola sentencia SQL y debe convertirse en handler
WASM (`handler/src/lib.rs` → `dist/handler.wasm`, function `create_invoice`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el runtime,
> calcula y devuelve *intenciones* (filas a insertar, comandos `_insert_invoice` / `_insert_line`
> a ejecutar) que el runtime valida y persiste en una **única transacción**. Todos los importes
> son decimales con `quantize(0.01)` (céntimos), nunca float.

> Contexto del módulo: facturas RECIBIDAS de proveedores (entrantes). Distinto del módulo fiscal
> `invoice` (emitidas por el hub). Ciclo de estado: `pending → validated → paid | cancelled`.

## 1. `create_invoice`  (command `supplier_invoices.invoices.create`)
Origen: `SupplierInvoiceService.create_invoice` + `SupplierInvoice.recalculate_total` +
`SupplierInvoiceLine.calculate`. Único handler `{type:wasm}` del módulo.

**Validación (espeja `schemas/create_invoice.json`, pero el WASM revalida):**
- `supplier_name` no vacío (error `missing_supplier`).
- `invoice_number` no vacío (error `missing_number`).
- `lines` lista no vacía (error `empty_lines`); cada línea con `description` (error
  `missing_description`).
- Parsear `invoice_date` / `due_date` (ISO `YYYY-MM-DD`, vacío o ausente → NULL; inválido →
  error `invalid_date`). `payment_date` se queda NULL en el alta (lo fija `mark_paid`).
- Parsear `tax_amount` como decimal (default `"0.00"`; inválido → error `invalid_amount`). El
  `tax_amount` viene dado en el payload (no se deriva de las líneas en este módulo).

**ID compartido cabecera + líneas (atomicidad):**
- El handler genera **un único `invoice_id`** (UUID v4 vía capacidad RNG del host) que comparten
  la cabecera (`:invoice_id`) y todas sus líneas (`:invoice_id` en `_insert_line`). En el legacy
  esto era el `flush()` que rellenaba la PK antes de crear las líneas; aquí el WASM lo predetermina
  para que no haga falta round-trip a BD. Cada línea recibe además su propio `:line_id` (UUID).

**Batch de N líneas + aritmética decimal fija (pieza 2 y 3):**
- Por cada línea: calcular `line_total` (pieza 2) y emitir una intención `_insert_line`
  (`{line_id, invoice_id, description, quantity, unit_price, line_total}`).
- `total_amount` = suma de los `line_total` (pieza 3), `quantize(0.01)`.
- Emitir la intención `_insert_invoice` (`{invoice_id, supplier_name, supplier_tax_id,
  invoice_number, invoice_date, due_date, total_amount, tax_amount, purchase_order_ref, notes}`),
  con `status='pending'` fijado por el SQL.
- El runtime ejecuta `_insert_invoice` + N×`_insert_line` en **una transacción**; si algo falla,
  no se persiste ni cabecera ni líneas.

**Devolver:** `{id, invoice_number, status:'pending', total_amount, tax_amount, lines_count}`.

**Binds que inyecta el runtime (no los aporta el WASM):** `:hub_id`, `:current_user_id`, `:now`
(en `_insert_invoice` y `_insert_line`). El WASM aporta `:invoice_id`, `:line_id` y todos los
campos calculados/parseados del payload.

**Evento:** tras commit, el runtime emite `supplier_invoices.invoice.created` (declarado en
`module.json`).

## 2. Cálculo de `line_total` por línea
Origen: `SupplierInvoiceLine.calculate`.
- `qty = Decimal(quantity)` (default `"1"`); `price = Decimal(unit_price)` (default `"0"`).
- `line_total = quantize(qty * price, 0.01)`.
- Este módulo **no** tiene descuento por línea ni tasa de IVA por línea (a diferencia de
  `quotes`/`sales`): la línea es simplemente cantidad × precio. El IVA agregado viene en el campo
  `tax_amount` de la cabecera, tal cual lo manda el payload.

## 3. Recálculo de `total_amount` de la cabecera
Origen: `SupplierInvoice.recalculate_total`.
- `total_amount = quantize(Σ line_total, 0.01)`.
- `tax_amount` NO se recalcula desde las líneas: se persiste el valor del payload (parseado en
  pieza 1). Es un dato declarado por quien introduce la factura del proveedor.

## 4. Comandos de transición (Tier 0 — ya resueltos, NO requieren WASM)
No son handlers WASM; quedan documentados para contexto del ciclo de vida. Son `transaction:true`
y deben llevar sus propias guardas de estado en SQL (`WHERE status = ...`) para evitar saltos
inválidos:
- `invoice_validate.sql` (`supplier_invoices.invoices.validate`): `pending → validated`.
  Emite `supplier_invoices.invoice.validated`.
- `invoice_mark_paid.sql` (`supplier_invoices.invoices.mark_paid`): `validated → paid`; fija
  `payment_date`. Emite `supplier_invoices.invoice.paid`.
- `invoice_cancel.sql` (`supplier_invoices.invoices.cancel`): `pending|validated → cancelled`.
  Emite `supplier_invoices.invoice.cancelled`.

> Si en el futuro alguna transición necesita lógica compuesta (p.ej. revertir un asiento contable,
> recalcular saldos de proveedor, o validar contra `purchase_order_ref` cruzando el módulo
> `purchase_orders` vía contrato de queries), esa pieza concreta subiría a un handler WASM
> análogo a `create_invoice`. Hoy no hace falta.
