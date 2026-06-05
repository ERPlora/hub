# quotes — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_quotes/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`).
Lo que sigue es lógica de cálculo / batch / atomicidad que **no** cabe en una sola
sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos
> `_insert_line` / `_set_status` a ejecutar) que el runtime valida y persiste en una
> transacción. Todos los importes son enteros de céntimos o decimales con `quantize(0.01)`.

## 1. `create_quote`  (command `quotes.quotes.create`)
Origen: `QuoteService.create_quote` + `Quote.recompute_totals` + `QuoteLine.recompute_line_total`.
- Validar: `customer_name` no vacío; `lines` lista no vacía; cada línea con `description`.
- Validar/parsear `valid_until` (ISO `YYYY-MM-DD` o vacío → NULL).
- Generar `quote_number` atómico → ver pieza 5 (counter).
- Por cada línea calcular `line_total` (pieza 3) y emitir `_insert_line`.
- Calcular `total_amount` / `tax_amount` agregados (pieza 4) y persistir cabecera + `_set_status` (status='draft').
- Devolver `{id, quote_number, status, total_amount, lines_count}`.

## 2. `update_quote_lines`  (command `quotes.quotes.update_lines`)
Origen: `QuoteService.update_quote_lines`.
- Guarda de estado: **solo** si el quote está en `draft` (si no → error `not_editable`).
- Reemplazo de líneas: soft-delete de las líneas actuales + insertar las nuevas (`_insert_line`).
- Recalcular totales (pieza 4) y `_set_status` (mismo status 'draft', nuevos totales).
- Lista vacía → error `empty_lines`.

## 3. Cálculo de `line_total` por línea
Origen: `QuoteLine.recompute_line_total`.
- `gross = quantize(quantity * unit_price, 0.01)`.
- Si `discount_pct > 0`: `gross = quantize(gross * (100 - discount_pct) / 100, 0.01)`.
- El impuesto va **incluido** en `unit_price` (convención m_sales) → no se suma aparte.

## 4. Recálculo de totales del quote (`total_amount`, `tax_amount`)
Origen: `Quote.recompute_totals`.
- `total_amount = Σ line_total`.
- `tax_amount`: por línea con `tax_rate > 0`, extraer el IVA incluido del bruto:
  `divisor = 1 + tax_rate/100`; `net = quantize(line_total / divisor, 0.01)`;
  `tax += quantize(line_total - net, 0.01)`. Sumar sobre todas las líneas.

## 5. Contador atómico de nº de cotización (`generate_quote_number`)
Origen: `QuoteCounter` + `generate_quote_number` (UPSERT `INSERT ... ON CONFLICT DO UPDATE
... RETURNING`). Formato `Q-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres.
- En hub-next se resuelve como capacidad del runtime (counter UPSERT) invocada por el
  handler; el WASM solo formatea `Q-{day}-{n:04d}` con el número devuelto.

## 6. `convert_to_order`  (command `quotes.quotes.convert_to_order`)
Origen: `QuoteService.convert_to_order`.
- Guarda de estado: **solo** desde `accepted` (si no → error `invalid_status`).
- Leer las líneas y construir el payload `sale_order`:
  `{customer_name, customer_email, customer_tax_id, notes: "From quote <num>", total_amount,
    items:[{product_name=description, is_service:true, quantity, price=unit_price, discount=discount_pct, tax_rate}]}`.
- Transicionar a `converted` (`_set_status`) y emitir `quotes.quote.converted` con el payload.
- Cross-module: el listener de `sales` (p.ej. `sales.create_sale`) consume el evento; quotes
  **no** importa de sales (sigue independiente — vía contrato de eventos, no de imports).

## 7. `expire_old_quotes`  (command `quotes.quotes.expire_old`, tarea programada)
Origen: `QuoteService.expire_old_quotes`.
- Seleccionar quotes con `status IN ('draft','sent')` y `valid_until IS NOT NULL` y `valid_until < hoy`.
- Marcar cada uno como `expired` (`_set_status`) y devolver `{expired:N, quote_numbers:[...]}`.
- `accepted`/`converted` nunca caducan. Operación batch sobre N filas → WASM (no una sola UPDATE
  por la necesidad de devolver la lista de números afectados y emitir un evento por lote).

## 8. Rastro en `notes` (Tier 1, no crítico)
Origen: `send_quote(email_to=...)`, `mark_rejected(reason=...)`.
- Hoy las transiciones simples (`quote_send.sql`, `quote_mark_rejected.sql`) NO escriben el
  rastro `[timestamp] Sent to X` / `[timestamp] Rejected: reason` en `notes`.
- Si se quiere conservar ese audit-trail textual, moverlo a un handler WASM que componga el
  nuevo `notes` (append con timestamp) — capacidad de "reloj" del host. No bloqueante.
