# accounting — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_accounting/{models.py,services.py,invariants.py}`. El CRUD plano
(alta de cuenta) y los listados/reportes ya están en SQL declarativo Tier 0 (`commands/*.sql`,
`queries/*.sql`). Lo que sigue es lógica de partida doble / contador atómico / contra-asiento /
invariantes que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el runtime,
> calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos a ejecutar) que el
> runtime valida y persiste en una transacción. Todos los importes son decimales con
> `quantize(0.01)` (céntimo). El `hub_id`, `created_by/at`, `updated_by/at` los inyecta el runtime.

## Convenciones de tipos de cuenta (de `models.py`)
- `ACCOUNT_TYPES = (asset, liability, equity, income, expense)`.
- `NORMAL_BALANCES = (debit, credit)`.
- `DEFAULT_NORMAL_BALANCE`: asset→debit, expense→debit, liability→credit, equity→credit, income→credit.
- `ENTRY_STATUSES = (draft, posted, cancelled)`.

---

## 1. `create_account`  (command `accounting.accounts.create`)
Origen: `AccountingService.create_account`. SQL Tier 0 disponible en `commands/account_create.sql`,
pero la validación + el cálculo de `normal_balance` van al handler, que produce los binds finales.
- Validar `account_type ∈ ACCOUNT_TYPES` (si no → error `invalid_type`).
- Validar `code` y `name` no vacíos (si no → error `missing_field`).
- Si `parent_id` no vacío: parsear UUID (error `invalid_parent_id`) y verificar que la cuenta padre
  existe en este hub (runtime hace el read; si no → error `parent_not_found`).
- Rechazar `code` duplicado por hub (runtime lee; si existe → error `duplicate_code`). El índice
  `uq_account_hub_code` es la red de seguridad.
- Inferir `normal_balance = DEFAULT_NORMAL_BALANCE[account_type]`.
- Emitir intención de insertar (binds: `code, name, account_type, parent_id, normal_balance`) ejecutando
  `account_create.sql`; emitir evento `accounting.account.created`.
- Devolver `{id, code, name, account_type, parent_id, normal_balance, created:true}`.

## 2. `create_entry`  (command `accounting.entries.create`)
Origen: `AccountingService.create_entry`. **Crítico**: aquí se enforce la partida doble.
- Parsear/validar `entry_date` (ISO `YYYY-MM-DD`; si no → error `invalid_date`).
- `lines` debe tener ≥2 elementos (si no → error `insufficient_lines`).
- Por cada línea (índice `idx`):
  - Parsear `account_id` a UUID (error `invalid_account_id`).
  - `debit = quantize(raw.debit, 0.01)`, `credit = quantize(raw.credit, 0.01)` (vacío/None → 0.00).
  - `debit < 0 || credit < 0` → error `negative_amount`.
  - `debit > 0 && credit > 0` → error `ambiguous_side` (solo un lado no-cero).
  - `debit == 0 && credit == 0` → error `zero_line`.
  - Acumular `total_debit += debit`, `total_credit += credit`.
- **Invariante de partida doble**: `total_debit == total_credit`; si no → `UnbalancedEntryError`
  (la transacción no persiste nada). Tolerancia: exacta en `create`, ±0.01 en el invariant de post.
- Todas las cuentas referenciadas deben existir y pertenecer a este hub (runtime lee por
  `account_id IN (...)`; las que falten → error `account_not_found` con la lista).
- Generar `entry_number` atómico (ver pieza 5).
- Insertar cabecera `accounting_journal_entry` (status='draft', `total_debit`, `total_credit`,
  `entry_number`, `entry_date`, `reference`, `description`) + una `accounting_journal_line` por línea
  (`entry_id`, `account_id`, `debit`, `credit`, `description`). Todo en una transacción.
- Emitir `accounting.entry.created`.
- Devolver `{id, entry_number, status:'draft', total_debit, total_credit, lines_count, created:true}`.

## 3. `post_entry`  (command `accounting.entries.post`)
Origen: `AccountingService.post_entry`. Promueve un asiento `draft` → `posted` (inicia el rastro fiscal).
- Parsear `entry_id` (error `invalid_entry_id`).
- Runtime lee el asiento; si no existe → error `not_found`.
- Solo `draft` puede contabilizarse; si `status != 'draft'` → error `not_draft`.
- Red de seguridad: re-comprobar `total_debit == total_credit`; si no → `UnbalancedEntryError`.
- Update: `status='posted'`, `posted_at = now`, `posted_by = current_user_id`.
- **Invariante `accounting.ledger_balanced`** (ver pieza 6): debe correr dentro del SAVEPOINT
  tras el cuerpo y antes del commit; si falla, rollback.
- Emitir `accounting.entry.posted`.
- Devolver `{id, entry_number, status:'posted', posted_at, posted:true}`.

## 4. `cancel_entry`  (command `accounting.entries.cancel`)
Origen: `AccountingService.cancel_entry`. Regla de rastro fiscal: un asiento `posted` es **inmutable**.
Para "deshacerlo" se crea un **contra-asiento** que invierte débito↔crédito y se marca el original
como `cancelled` (nunca se borra).
- Parsear `entry_id` (error `invalid_entry_id`). Runtime lee asiento; si no → error `not_found`.
- `status == 'cancelled'` → error `already_cancelled`.
- `status == 'draft'` → error `draft_entry` (un borrador no se cancela, se ignora/borra).
- Runtime lee las líneas del asiento original.
- Generar `contra_number` atómico (pieza 5).
- Insertar contra-asiento (`status='posted'`, `posted_at=now`, `entry_date` = la del original,
  `reference = "Reversal of <entry_number>"`,
  `description = "Contra-entry for <entry_number>" [+ " — <reason>"]`,
  `total_debit = original.total_credit`, `total_credit = original.total_debit`).
- Insertar una línea contra por cada línea original **intercambiando lados**:
  `debit = orig.credit`, `credit = orig.debit`, `description = "Reversal: <orig.description>"`.
- Marcar el original `status='cancelled'` y anexar `\n[CANCELLED] <reason>` (o `\n[CANCELLED]`) a
  su `description`.
- **Invariante `accounting.ledger_balanced`** debe verificarse tanto sobre el original como sobre
  el contra-asiento (rol "entry" y "contra_entry").
- Emitir `accounting.entry.cancelled`.
- Devolver `{id, entry_number, status:'cancelled', contra_entry_id, contra_entry_number, cancelled:true}`.

## 5. Contador atómico de nº de asiento (`_next_entry_number`)
Origen: `_next_entry_number` + modelo `EntryCounter` (tabla `accounting_entry_counter`).
- Formato: `YYYY-NNNNNN` (`year` = año UTC actual; `NNNNNN` = secuencia por hub+año, 6 dígitos).
- UPSERT atómico (`INSERT ... ON CONFLICT (hub_id, year) DO UPDATE SET last_number = last_number + 1
  RETURNING last_number`) — sin ventana SELECT→UPDATE en SQLite **y** Postgres.
- En hub-next se resuelve como capacidad del runtime (counter UPSERT sobre `accounting_entry_counter`)
  invocada por el handler; el WASM solo formatea `{year}-{n:06d}` con el número devuelto y aporta el
  "reloj" (año UTC) vía capacidad del host.

## 6. Invariante `accounting.ledger_balanced`
Origen: `invariants.py` (`accounting_ledger_balanced` / `_check_entry_balanced`). Declarado por
`post_entry` y `cancel_entry`. Corre dentro del SAVEPOINT del comando, antes del commit.
- Para el asiento afectado (id en payload o resultado): el runtime re-lee la cabecera + sus líneas.
- Comprobar `|Σ debit − Σ credit| ≤ 0.01` (tolerancia de un céntimo por redondeo Decimal). Si excede
  → Violation `accounting.ledger_balanced` (rollback).
- Defensa en profundidad: los totales de cabecera (`total_debit`/`total_credit`) deben coincidir con
  la suma de las líneas dentro de la misma tolerancia; si derivan → Violation (regresión del comando).
- En `cancel_entry`, verificar **además** el contra-asiento (rol "contra_entry") de forma independiente.
- Si no hay `entry_id` (el comando cortocircuitó antes de actuar), el invariante no aplica (None).

## 7. Reportes con cálculo del 'net' (Tier 1, no crítico)
Origen: `AccountingService.get_account_balance` / `get_trial_balance`.
- El balance de comprobación (`queries/trial_balance.sql`) ya agrega débitos/créditos por cuenta
  desde asientos `posted`, con cota opcional `end_date`. El cálculo del **net por cuenta**
  (`net = total_debit − total_credit` si `normal_balance='debit'`, e inverso si `'credit'`) y el flag
  agregado `is_balanced` (`Σ debit == Σ credit`) los hace hoy el UI/SDK a partir de las filas.
- `get_account_balance` (saldo de una sola cuenta con su `net` firmado) puede servirse con una query
  análoga filtrada por `account_id`, o calcularse en el SDK; no requiere WASM. Solo escalar a un
  handler si en el futuro se quiere devolver el `net` ya firmado desde el backend en un solo paso.

## 8. FiscalYear (modelo presente, sin acciones en el servicio legacy)
- `models.py` define `FiscalYear` (tabla `accounting_fiscal_year`, creada en `001_init.sql`) con
  `is_closed` para bloquear apuntes en periodos cerrados, pero `services.py` **no** expone ninguna
  acción de alta/cierre. No se ha portado superficie de comando para evitar contrato muerto.
- Cuando se implemente: alta de ejercicio (CRUD Tier 0) + cierre (`close_fiscal_year`) y, en
  `create_entry`/`post_entry`, una guarda que rechace asientos cuya `entry_date` caiga en un
  ejercicio `is_closed=1` (invariante de periodo) → handler WASM.
