# general_ledger — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_general_ledger/{models.py,services.py}`. El CRUD plano (alta de
cuenta / centro de coste / periodo, cierre y reapertura de periodo) ya está en SQL declarativo
Tier 0 (`commands/*.sql`). Las consultas, incluido el balance de comprobación, son agregaciones
de solo lectura y viven en `queries/*.sql` (Tier 0). Lo que sigue es lógica contable de
validación / atomicidad / batch que **no** cabe en una sola sentencia SQL y debe convertirse en
handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el runtime
> (cuenta/periodo/líneas), valida, calcula y devuelve *intenciones* (filas a insertar/actualizar,
> número de asiento a través del counter del host) que el runtime valida y persiste en una sola
> transacción. Todos los importes son decimales con `quantize(0.01)` (Numeric(15,2)).

## Invariant crítico (todo el módulo)

**Partida doble: `sum(debits) == sum(credits)`** por asiento. Es la guarda de corrección central
(`UnbalancedLedgerEntryError`). Se valida en `create_entry` y se re-verifica en `post_entry`.
Convención de signo del plan (`DEFAULT_NORMAL_BALANCE`): asset/expense → `debit`; liability/
equity/income → `credit` (usado para inferir `normal_balance` al crear cuenta y para el neto del
balance de comprobación).

---

## 1. `create_entry`  (command `general_ledger.entries.create`)
Origen: `GeneralLedgerService.create_entry`.
- Parsear/validar `entry_date` (ISO `YYYY-MM-DD`).
- Resolver `period_id` → debe existir (error `period_not_found`).
- `lines`: requiere **≥ 2** (error `insufficient_lines`).
- Por cada línea:
  - `account_id` válido; `cost_center_id` opcional.
  - `debit`/`credit` ≥ 0 (error `negative_amount`).
  - **Exactamente uno** de debit/credit no-cero: ambos > 0 → `ambiguous_side`; ambos == 0 → `zero_line`.
  - Acumular `total_debit` / `total_credit`.
- **Cuadre**: `total_debit == total_credit` o lanzar `UnbalancedLedgerEntryError` (error `unbalanced`).
- **Existencia de cuentas**: todas las `account_id` deben pertenecer al hub (error `account_not_found`
  con la lista de las que faltan). El runtime hace el read; el WASM compara conjuntos.
- **No asentar sobre cuentas agregadoras**: si alguna cuenta tiene `is_summary=1` → error
  `summary_account` con la lista de códigos.
- **Existencia de centros de coste** referenciados (error `cost_center_not_found`).
- Generar `entry_number` atómico → ver pieza 4 (counter).
- Persistir cabecera `general_ledger_entry` (status `'draft'`, totales cacheados) + emitir
  `_insert_line` por cada línea parseada.
- Devolver `{id, entry_number, status:'draft', period_id, total_debit, total_credit, lines_count, created:true}`.
- Emite evento `general_ledger.entry.created`.

## 2. `post_entry`  (command `general_ledger.entries.post`)
Origen: `GeneralLedgerService.post_entry`.
- Leer asiento (error `not_found`).
- Guarda de estado: **solo** `draft` puede postearse (si no → error `not_draft`).
- Leer su periodo: debe existir (`period_not_found`) y estar **`open`** (si `closed` → error
  `period_closed`).
- Re-verificar cuadre `total_debit == total_credit` (defensivo → `unbalanced`).
- Transición: `status='posted'`, `posted_at=now` (capacidad reloj del host).
- Devolver `{id, entry_number, status:'posted', posted_at, posted:true}`.
- Emite evento `general_ledger.entry.posted`.

## 3. `reverse_entry`  (command `general_ledger.entries.reverse`)
Origen: `GeneralLedgerService.reverse_entry`. **Contra-asiento — rastro fiscal, batch.**
- Leer asiento (error `not_found`).
- Guardas de estado: `reversed` → `already_reversed`; `draft` → `draft_entry` (un borrador se
  ignora/borra, no se revierte).
- Periodo debe existir y estar **`open`** (error `period_closed`).
- Leer las líneas del asiento original.
- Generar `contra_number` atómico (pieza 4).
- Crear un nuevo asiento **`posted`** en la **misma fecha** y **mismo periodo**:
  - `reference = "Reversal of <entry_number>"`,
  - `description = "Contra-entry for <entry_number>"` (+ ` — <reason>` si hay reason),
  - `total_debit = original.total_credit`, `total_credit = original.total_debit`,
  - `posted_at = now`.
- Por cada línea original, emitir `_insert_line` en el contra-asiento **con debit/credit
  intercambiados** (eso lo convierte en contra-asiento); conservar `account_id` y `cost_center_id`;
  `description = "Reversal: <desc original>"`.
- Marcar el original `status='reversed'` y anexar `\n[REVERSED] <reason?>` a su `description`.
- Devolver `{id, entry_number, status:'reversed', contra_entry_id, contra_entry_number, reversed:true}`.
- Emite evento `general_ledger.entry.reversed`.
- Atomicidad obligatoria: original + contra-asiento + sus líneas en una sola transacción.

## 4. Contador atómico de nº de asiento (`_next_entry_number`)
Origen: `_next_entry_number` + modelo `LedgerEntryCounter` (UPSERT `INSERT ... ON CONFLICT
DO UPDATE ... RETURNING`). Formato **`GL-YYYY-NNNNNN`** (NNNNNN = secuencia por hub+año, 6 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres.
- En hub-next se resuelve como **capacidad del runtime** (counter UPSERT sobre
  `general_ledger_entry_counter` por `(hub_id, year)`) invocada por el handler; el WASM solo
  formatea `GL-{year}-{n:06d}` con el número devuelto. Lo usan tanto `create_entry` como
  `reverse_entry` (el contra-asiento consume otro número).

---

## Notas Tier 0 (ya implementado en SQL, sin WASM)

- **Inferencia de `normal_balance`** al crear cuenta: el origen lo deriva de `account_type`
  (`DEFAULT_NORMAL_BALANCE`). `account_create.sql` recibe `:normal_balance` ya resuelto; si el
  payload lo omite, el runtime/SDK debe inferirlo antes del bind (asset/expense=debit, resto=credit).
- **Validación de rango de fechas** del periodo (`end_date >= start_date`) y unicidad de
  `name`/`code`: la unicidad la garantizan los índices; el rango lo valida el runtime/SDK al
  preparar el bind (no necesita WASM, es un check escalar).
- **Balance de comprobación** (`get_trial_balance`), **saldo de cuenta** (`get_account_balance`)
  y **movimientos de cuenta** (`get_account_movements`): son agregaciones de solo lectura sobre
  asientos `posted`. Viven en `queries/trial_balance.sql` y `queries/account_movements.sql`
  (Tier 0). El **neto firmado** por `normal_balance` y el flag **`is_balanced`** global se
  componen en el SDK/UI a partir de los agregados por cuenta (ver `erp-general-ledger-reports`).
  `get_account_balance` (saldo de una sola cuenta con `as_of_date`) puede derivarse de la query
  de movimientos en el cliente; no se expone como query/command separado para no duplicar.
