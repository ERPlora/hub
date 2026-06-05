# orders — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_orders/{models.py,services.py,hooks.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0 (`commands/*.sql`):
`orders_order` (tabla PROPIA del módulo), `orders_settings`, `orders_note`.
Lo que sigue es lógica de validación / transición / integración cross-module que **no** cabe
en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next (§2.3, §5.3): el WASM **nunca toca la BD** y **nunca** lee/escribe la tabla
> privada de otro módulo (p.ej. `sales_sale`). Recibe el payload + datos leídos por el runtime
> (lecturas a `orders_*` propias o a queries PÚBLICAS de otros módulos como `sales.sales.get`),
> calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos internos
> `_note_status_change` / `order_set_status` a ejecutar, eventos a emitir) que el runtime valida
> y persiste en una transacción. El cruce con `sales` es por **contrato/evento**, no por import
> ni por UPDATE directo.

## 1. `create_order`  (command `orders.create`, emit `orders.order_created`)
Origen: `OrderService.create`.
- En legacy esto creaba un `Sale` borrador con `source_module='orders'`. En hub-next el módulo
  OWNea su pedido: el handler crea una fila en `orders_order` (su tabla), **no** una venta.
- Validar/parsear `requested_date` (ISO `YYYY-MM-DD`): error `invalid_date_format` si no parsea;
  error `delivery_date_in_past` si `requested_date < hoy` (capacidad "reloj" del host).
- Derivar `status` inicial: leer `orders_settings` (vía runtime); `'pending'` si `auto_confirm`,
  si no `'draft'`.
- Si `orders_settings.require_customer` y no hay `customer_name`/`customer_phone` → error `customer_required`.
- Generar `order_number` atómico (formato p.ej. `O-YYYYMMDD-NNNN`) vía capacidad counter del
  runtime (UPSERT atómico, mismo patrón que quotes §5) — el WASM solo formatea el número devuelto.
- Emitir intención de insertar la cabecera en `orders_order` (channel, priority, customer_*,
  delivery_address, requested_date/time, notes, internal_notes, total=0, sale_id=NULL) +
  una nota `status_change` inicial (`to_status=status`, content `Order created (<channel>)`).
- `sale_id` queda NULL: la venta real se vincula después por evento (ver pieza 4).
- Devolver `{id, order_number, status, total}`.
- Las líneas/`items` del pedido: si se modelan, requieren su propia tabla `orders_order_item`
  (no `sales_sale_item`, que es privada de sales). Hoy fuera de alcance Tier 0.

## 2. `complete_order`  (command `orders.complete`, emit `orders.order_completed`)
Origen: `OrderService.complete_order` (+ `SaleService.complete_draft`).
- Guarda de estado: **solo** desde `draft` o `pending` (si no → error `not_completable`).
- Transición de `orders_order` a `completed` vía comando interno `order_set_status`
  (`:order_id`, `:new_status='completed'`).
- Escribir la nota `status_change` (pieza 3): lee el estado anterior, compone el texto
  `Order completed[: reason]`.
- Efecto sobre la venta vinculada (cerrar/cobrar la venta): es responsabilidad de `sales`, NO de
  orders. Se modela como integración diferida (pieza 5): si `sale_id` no es NULL, emitir un evento
  de contrato (`orders.order_completed` con `{order_id, sale_id}`) que el listener de `sales`
  consume para cerrar/checkout su venta. orders **no** hace `complete_draft` sobre `sales_sale`.

## 3. Nota de cambio de estado + reglas de transición (`_note_status_change`)
Origen: `OrderService._record_status_change`, `confirm_order`, `cancel_order`.
- Los comandos Tier 0 `orders.confirm` (draft→pending) y `orders.cancel` (→voided) solo hacen el
  `UPDATE orders_order` (`commands/order_set_status.sql`) con `:order_id` + `:new_status` que envía
  la UI. **No** escriben la nota `status_change`.
- La parte que necesita WASM:
  - **Validar la transición** leyendo el estado actual de `orders_order`:
    `confirm` solo desde `draft` (error `only_draft_confirmable`);
    `cancel` no desde `completed`/`voided` (error `cannot_cancel_finalized`) y, si el pedido tiene
    una venta pagada vinculada, error `cannot_cancel_paid` (consultar estado de pago vía contrato
    `sales.sales.get(sale_id)`, nunca leyendo `sales_sale`).
  - **Componer y persistir** la nota vía el comando interno `orders._note_status_change`
    (`commands/note_status_change.sql`): resolver `:from_status` (estado leído antes del cambio),
    `:to_status` (= new_status), `:content` (`Order confirmed/cancelled[: reason]`, usa el `reason`
    del payload de la UI) y `:new_id` (uuid generado por el host).
- Es decir: el handler hace validación-transición → `order_set_status` → `_note_status_change`,
  todo en la misma transacción (atomicidad), y emite `orders.order_confirmed` / `orders.order_cancelled`.

## 4. `link_to_sale`  (command `orders.link_to_sale`, listen `sales.after_checkout`)
Origen: `hooks.py::_link_order_to_sale`.
- Disparado por el evento `sales.after_checkout` que emite `sales` al cerrar una venta (payload con
  `sale_id` + metadatos de origen, p.ej. `order_id`/`order_number`).
- El handler resuelve a qué pedido corresponde y emite la intención de UPDATE sobre `orders_order`
  fijando `sale_id` (+ opcionalmente `total`/`status` derivados del evento).
- Cross-module estricto: orders **no** lee `sales_sale`; toda la info llega en el payload del evento
  (contrato) o, si hace falta más, vía la query pública `sales.sales.get`. No hay import de `sales`.
- Idempotencia: si el pedido ya tiene `sale_id`, no-op (evitar doble vínculo en reintentos del bus).

## 5. Integración con `sales` (efecto sobre la venta) — contrato/evento, no UPDATE
Origen: el legacy mutaba `Sale` directamente (`sale.status=...`, `SaleService.complete_draft`).
- PROHIBIDO en hub-next: orders no puede `UPDATE sales_sale`. El antiguo `commands/sale_set_status.sql`
  se eliminó por esto.
- El efecto sobre la venta (cerrarla al completar el pedido, anularla al cancelar) se modela como
  **lógica de integración diferida**: orders emite un evento de su propio namespace
  (`orders.order_completed` / `orders.order_cancelled`) con `{order_id, sale_id, reason}`; un listener
  del módulo `sales` lo consume y aplica el cambio sobre SU tabla con SUS comandos.
- orders solo gestiona su `orders_order` + bitácora; la venta es autoridad de `sales`.

## 6. `update_settings` (Tier 0, ya cubierto)
Origen: `OrderService.update_settings` (get-or-create). Resuelto con `commands/settings_upsert.sql`
(UPSERT por `hub_id`). La UI reenvía SIEMPRE el conjunto completo de campos, así que no hace falta
el merge campo-a-campo del legacy ni WASM.
