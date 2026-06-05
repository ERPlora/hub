# banking — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_banking/{models.py,services.py,invariants.py}`. El CRUD plano
(alta de cuenta, conciliar/desconciliar apuntes) y todas las lecturas ya están en SQL
declarativo Tier 0 (`queries/*.sql`, `commands/account_create.sql`,
`commands/transaction_reconcile.sql`, `commands/transaction_unreconcile.sql`).
Lo que sigue es lógica de mantenimiento de saldo, invariantes financieros y recálculo
agregado que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. Todos los importes son decimales con
> `quantize(0.01)` (saldos `Numeric(14,2)`). `amount` lleva **signo**: + entrada / - salida.

## 1. `add_transaction`  (command `banking.transactions.add`)
Origen: `BankingService.add_transaction`. Es el único punto donde el dinero se mueve, por eso
es WASM y no un INSERT plano: inserta el apunte **y** actualiza el saldo cacheado de la cuenta
en la misma transacción (dos filas correlacionadas → no es una sola sentencia).

Entradas (payload validado por `schemas/transaction_add.json`):
`account_id, transaction_date (ISO YYYY-MM-DD), value_date (ISO o null), amount (signed),
description, counterparty, reference, source ∈ {manual,import,api}`.

Lógica:
- El runtime lee la cuenta destino (`banking.accounts.get` interno) dentro de la transacción.
  Si no existe → error `account_not_found`.
- Parsear/validar `transaction_date` y `value_date` (ya forzado por el schema `format: date`,
  pero el handler revalida ISO; `value_date` opcional → NULL).
- Validar `source` ∈ {manual,import,api} (también cubierto por el enum del schema).
- `amt = Decimal(amount).quantize(0.01)`.
- Emitir intención **INSERT** en `banking_transaction` con:
  `id=:new_id, hub_id, account_id, transaction_date, value_date, amount=amt,
   description, counterparty, reference, source, is_reconciled=0,
   created_by=:current_user_id, created_at=:now, updated_at=:now`.
- Emitir intención **UPDATE** en `banking_account` (la cuenta que OWNea este módulo):
  `current_balance = quantize(current_balance + amt, 0.01),
   updated_by=:current_user_id, updated_at=:now`.
- Devolver `{id, account_id, amount, transaction_date, current_balance, created:true}`.
- Tras el cuerpo, dentro del SAVEPOINT, ejecutar el invariant de la pieza 3.
- Emite `banking.transaction.added`.

## 2. Invariant financiero `banking.balance_matches_movements`
Origen: `old_modules/m_banking/invariants.py`. Declarado por `add_transaction`,
`reconcile_transaction` y `unreconcile_transaction` (legacy `risk_tier=3`,
`financial_impact=True`). Debe registrarse como invariant del runtime y dispararse dentro del
SAVEPOINT de esos commands, **antes** del commit; cualquier violación hace rollback.

Regla: para la cuenta tocada por la acción,
`opening_balance + Σ(banking_transaction.amount)` debe igualar el `current_balance`
almacenado, con **tolerancia de 0.01** (un céntimo de redondeo Decimal). Mayor delta = bug.

Resolución de la cuenta a verificar:
- `add_transaction` → `account_id` viene en payload y resultado.
- `reconcile`/`unreconcile` → solo traen `transaction_id`; el runtime busca el apunte
  (scope `hub_id`) para descubrir su `account_id`. (Conciliar/desconciliar **no** mueven
  dinero — solo voltean `is_reconciled` — así que el invariant aquí es pura post-condición:
  el saldo ya era correcto y debe seguir siéndolo.)
- El `Σ(amount)` se calcula a nivel SQL (`func.sum`), no cargando filas en memoria
  (una cuenta puede tener miles de apuntes).
- La suma se lee **dentro** del SAVEPOINT (las filas recién escritas son visibles).
- Si no se puede resolver la cuenta → el invariant devuelve `None` (la ruta de error
  upstream ya cubrió ese caso); cuenta no encontrada tras la acción → `Violation`.

Mensaje de violación: incluye `opening_balance`, `movements_sum`, `computed_current`,
`stored_current`, `delta`, `tolerance` en el contexto (igual que el legacy).

## 3. `get_account_balance` con `as_of_date` (recálculo histórico)
Origen: rama con `as_of_date` de `BankingService.get_account_balance`.
- **Sin** `as_of_date`: ya resuelto por la query Tier 0 `banking.accounts.get`
  (devuelve el `current_balance` cacheado). No necesita WASM.
- **Con** `as_of_date`: hay que recomputar `opening_balance + Σ(amount)` de los apuntes con
  `transaction_date <= as_of_date`. Es un agregado parametrizado por fecha que devuelve un
  escalar calculado (no una fila tal cual) → conviene un handler WASM (o, si el runtime
  expone una capacidad de "query agregada con bind", podría ser Tier 1). Entradas:
  `account_id, as_of_date (ISO)`. Salida: `{account_id, balance, as_of_date, currency}`.
  Validar `as_of_date` ISO → error `invalid_as_of_date`; cuenta inexistente → `account_not_found`.

## 4. Conciliación por sesión (`BankReconciliation`) — PENDIENTE de definir commands
El modelo `BankReconciliation` (tabla `banking_reconciliation`, ya creada en
`migrations/sqlite/001_init.sql`: `account_id, statement_date, statement_balance,
status ∈ {open,closed}`) **no tiene servicios en el legacy** (`services.py` solo expone los
toggles `is_reconciled` por apunte). La tabla se porta para preservar el esquema, pero **no**
hay commands/queries declarados todavía (por eso no hay entrada de navegación ni schema
colgante para ella). Cuando se diseñe el flujo de cierre de extracto, añadir aquí:
- `open_reconciliation` (INSERT sesión status='open' para una cuenta + statement_date/balance).
- `close_reconciliation` (validar que la suma de apuntes conciliados ≤ statement_date cuadra
  con `statement_balance` dentro de tolerancia; status → 'closed'). Esa comparación cruzada
  (sesión ↔ Σ apuntes conciliados) sería lógica WASM, no un UPDATE plano.

> Nota: ningún handler aquí lee/escribe tablas de otros módulos. `banking` OWNea
> `banking_account`, `banking_transaction` y `banking_reconciliation`; el saldo se mantiene
> solo dentro de este módulo.
