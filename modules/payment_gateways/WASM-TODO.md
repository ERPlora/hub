# WASM-TODO — payment_gateways (Tier 2)

Lógica de `modules/m_payment_gateways/services.py` (`PaymentGatewayService`) y
`models.py` que **no** es CRUD declarativo y debe convertirse en handler
Rust→WASM (Extism). El WASM no toca la BD: recibe el payload + filas leídas y
devuelve *intenciones* (inserts/updates) que el runtime valida y ejecuta.
Mapeo a `dist/handler.wasm` con las funciones declaradas en `module.json`.

## 1. `initiate_payment` → función WASM `initiate_payment`
Command `payment_gateways.transactions.initiate`.
Por qué no es Tier 0:
- **Mintado atómico de referencia** `PT-YYYYMMDD-NNNN` (`generate_transaction_reference`
  + tabla `payment_gateways_counter`): upsert `INSERT ... ON CONFLICT(hub_id,day)
  DO UPDATE SET last_number = last_number + 1 RETURNING last_number`. Es un contador
  atómico per-hub-per-día, no expresable como un INSERT declarativo simple.
- Validaciones de negocio previas: gateway existe y `is_active`; `amount` > 0 y
  parseable a Decimal(15,2); `currency` no vacío y, si la pasarela declara
  `supported_currencies`, que la divisa esté en la lista.
- Normalización: `amount` cuantizado a 2 decimales, `currency` a mayúsculas,
  `payment_method_type` por defecto `card`.
Salida: nueva fila en `payment_gateways_transaction` con `status='pending'` +
la `reference` minteada. Emite `payment_gateways.transaction.initiated`.

## 2. `mark_succeeded` → función WASM `mark_succeeded`
Command `payment_gateways.transactions.mark_succeeded`.
Por qué no es Tier 0:
- **Máquina de estados**: solo permite la transición desde `pending`/`processing`
  → `succeeded`; cualquier otro estado se rechaza (`invalid_state`).
- Requiere `provider_transaction_id` no vacío; setea `transaction_id`,
  `raw_response` (JSON), `captured_at = now`, y limpia `error_code`/`error_message`.

## 3. `mark_failed` → función WASM `mark_failed`
Command `payment_gateways.transactions.mark_failed`.
Por qué no es Tier 0:
- Misma **máquina de estados** que `mark_succeeded` pero hacia `failed`
  (solo desde `pending`/`processing`); guarda `error_code`, `error_message`,
  `raw_response`.

## 4. `refund_transaction` → función WASM `refund_transaction`
Command `payment_gateways.transactions.refund`.
Por qué no es Tier 0 (la pieza más compleja):
- **Aritmética de reembolso parcial**: suma `amount_refunded` de los reembolsos
  en `succeeded` (`total_refunded`), calcula `remaining = amount - already_refunded`,
  valida que el monto pedido (o el `remaining` completo si no se pasa monto) sea
  > 0 y no exceda `remaining`. Todo en Decimal(15,2).
- **Máquina de estados doble**: la transacción debe estar en `succeeded` o
  `partially_refunded`; la pasarela enlazada debe tener `supports_refunds`.
- **Escritura multi-fila transaccional**: inserta una fila en
  `payment_gateways_refund` (`status='succeeded'`, `refunded_at=now`) Y actualiza
  la transacción a `refunded` (si new_total >= amount) o `partially_refunded`.
Emite `payment_gateways.transaction.refunded`.

## 5. `get_transactions_summary` → función WASM `transactions_summary`
Query/command `payment_gateways.transactions.summary`.
Por qué no es Tier 0:
- **Agregación con lógica de presentación**: ventana temporal `period_days`
  (default 30), breakdown por estado (count + sum(amount) por cada uno de los 6
  estados), `total_count`, `succeeded_volume` (suma de `succeeded` +
  `partially_refunded`), y `refunded_volume` (suma de reembolsos `succeeded` en
  el periodo). Combina dos agregados distintos (transacciones + reembolsos) y
  rellena estados con 0 — más expresivo de lo razonable en una sola .sql Tier 0.

## 6. Enmascarado de secretos — `mask_config` (models.py)
No es un command, pero es lógica que debe ejecutarse en Rust/WASM al **serializar**
cualquier pasarela hacia el cliente: redacta a `"***"` los valores de claves
sensibles (`api_key`, `secret_key`, `publishable_key`, `private_key`,
`client_secret`, `merchant_key`, `webhook_secret`, `password`, `token`,
match case-insensitive por substring). La query `gateways_list.sql` devuelve el
JSON crudo de `config`; el host/WASM debe enmascararlo antes de exponerlo. El WC
NUNCA debe pintar `config` sin pasar por esta capa.

## Navegación / queries de transacciones (uso futuro)

La entrada de navegación `transactions` se **eliminó** de `module.json`
(2026-06-02): apuntaba al componente `erp-payment-gateways-gateways`, que solo
tiene su propio `.tsx` para la vista de gateways — no existe una vista de
transacciones (`erp-payment-gateways-transactions`), así que era una entrada
muerta. Las queries `payment_gateways.transactions.list`
(`queries/transactions_list.sql`), `payment_gateways.transactions.get`
(`queries/transaction_get.sql`) y `payment_gateways.transactions.refunds`
(`queries/refunds_for_transaction.sql`) **se dejan declaradas** en `module.json`
para uso futuro: cuando se cree el WC `erp-payment-gateways-transactions`, basta
con re-añadir la entrada de navegación apuntándolo y consumir estas queries (no
hace falta volver a declararlas).

## Notas de migración
- La tabla `payment_gateways_counter` se incluye en `001_init.sql` para que el
  handler de mintado tenga dónde persistir el contador, aunque ningún command
  declarativo la toca.
- El módulo es **provider-agnóstico**: no integra ningún SDK de pago. Las llamadas
  reales al proveedor (Stripe/Redsys/PayPal) son Tier 1 (host capability
  `http.fetch` mediado) o adapters externos; aquí solo se modela el ciclo de vida.
- `routes.py` legacy → reemplazado por el WC Stencil + SDK (no se migra).
