# bank_reconciliation — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_bank_reconciliation/{models.py,services.py}`. El CRUD plano
ya está en SQL declarativo Tier 0 (`commands/*.sql`, `queries/*.sql`). Lo que sigue es
lógica de batch / atomicidad condicional / matching heurístico que **no** cabe en una sola
sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el runtime
> ya leyó (líneas del extracto, matches existentes), calcula y devuelve *intenciones* (filas a
> insertar/actualizar/soft-delete y eventos a emitir) que el runtime valida y persiste en una
> transacción. Importes con `quantize(0.01)`; fechas ISO `YYYY-MM-DD`.

## Comandos enrutados a WASM (declarados en `module.json`)

| command | function | origen legacy |
|---|---|---|
| `bank_reconciliation.statements.create` | `create_statement` | `ReconciliationService.create_statement` |
| `bank_reconciliation.matches.remove` | `remove_match` | `ReconciliationService.remove_match` |
| `bank_reconciliation.matches.auto_match` | `auto_match_by_amount_and_date` | `ReconciliationService.auto_match_by_amount_and_date` |
| `bank_reconciliation.statements.close` | `close_statement` | `ReconciliationService.close_statement` |

---

## 1. `create_statement`  (command `bank_reconciliation.statements.create`)
Origen: `ReconciliationService.create_statement`.

Por qué WASM (no Tier 0): genera el `statement_number` cuando viene vacío y persiste un
**batch** de líneas iniciales en la misma transacción que la cabecera.

- Validar: `bank_account_ref` no vacío (→ error `missing_account`).
- Parsear/validar fechas (`statement_date`, `period_start`, `period_end`): ISO o vacío→NULL
  (→ error `invalid_date`).
- Parsear/validar `opening_balance` / `closing_balance` como decimal (→ error `invalid_amount`).
- **Nº de extracto**: si `statement_number` viene vacío, generar
  `f"{bank_account_ref}-{utcnow:%Y%m%d%H%M%S%f}"` (único por hub). La unicidad por
  `(hub_id, statement_number)` la garantiza el índice `uq_bank_recon_stmt_number_per_hub`;
  el reloj es una capacidad del host (el WASM solo formatea con el timestamp recibido).
- Emitir intención de insertar la cabecera (`status='draft'`).
- Por cada línea en `lines` (opcional): parsear `transaction_date` (→ `invalid_line_date`) y
  `amount` (→ `invalid_line_amount`); emitir `_insert_line` (`is_matched=0`). Reutiliza el
  contrato de `commands/statement_line_add.sql`.
- Devolver `{id, statement_number, bank_account_ref, status, lines_count}`.
- Emite `bank_reconciliation.statement.created`.

## 2. `remove_match`  (command `bank_reconciliation.matches.remove`)
Origen: `ReconciliationService.remove_match`.

Por qué WASM: borra el match y, **condicionalmente**, revierte `is_matched` de la línea
solo si no le quedan otros matches — requiere leer el conteo restante y decidir.

- Cargar el match por `match_id` (scoping hub_id lo hace el runtime; → `not_found` si no existe).
- Guardar `statement_line_id = match.statement_line_id`.
- Soft-delete del match (`is_deleted=1`, `deleted_at=now`).
- Contar matches restantes (no borrados) de esa `statement_line_id`.
  - Si quedan **0**: emitir intención de `UPDATE` de la línea → `is_matched=0`, `matched_at=NULL`.
  - Si quedan ≥1: dejar la línea como está.
- Devolver `{removed:true, statement_line_id}`.
- Emite `bank_reconciliation.match.removed`.

## 3. `auto_match_by_amount_and_date`  (command `bank_reconciliation.matches.auto_match`)
Origen: `ReconciliationService.auto_match_by_amount_and_date`.

Por qué WASM: matching greedy **batch** entre N líneas no conciliadas y M candidatos, con
tolerancia de fechas; cada candidato se consume como máximo una vez. No expresable en SQL.

Entrada: `statement_id`, `candidate_entries: [{ref, amount, date}]`, `tolerance_days` (def. 2).
Filas que el runtime debe leer y pasar al WASM: las líneas del extracto con `is_matched=0`,
ordenadas por `transaction_date ASC` (= `queries/unmatched_lines_list.sql` con ese statement).

Algoritmo (idéntico al legacy):
- Validar `statement_id` existe (→ `not_found`) y `tolerance_days >= 0` (→ `invalid_tolerance`).
- Normalizar candidatos: cada uno necesita `ref` (acepta alias `ledger_entry_ref`) → si falta,
  error `missing_ref`; parsear `amount` (→ `invalid_amount`) y `date` (→ `invalid_date`).
- Para cada línea no conciliada, recorrer candidatos no consumidos y elegir el **primero** que:
  1. tenga `amount` **exactamente igual** al de la línea (comparación decimal, no float), y
  2. ambos tengan fecha y `abs(line.date - cand.date) <= tolerance_days`;
     si **solo uno** de los dos tiene fecha → se **descarta** (no se puede validar tolerancia);
     si **ninguno** tiene fecha → se acepta (solo importe).
  Al casar: marcar el candidato como consumido y registrar el par (line, cand). `break`.
- Por cada par casado emitir:
  - intención de `_insert_match` (`match_type='auto'`, `confidence_score=0.900`,
    `amount_matched = line.amount`, `notes="auto-match: amount+date"`), y
  - intención de `UPDATE` de la línea → `is_matched=1`, `matched_at=now`.
- Devolver `{statement_id, matched_count, match_ids:[...]}`.
- Emite `bank_reconciliation.match.created` (uno por lote o por match, según el bus).

## 4. `close_statement`  (command `bank_reconciliation.statements.close`)
Origen: `ReconciliationService.close_statement`.

Por qué WASM: transición de estado con **guarda** que depende de un conteo agregado (no puede
cerrar si quedan líneas sin conciliar) y devuelve ese conteo en el error.

- Cargar el extracto por `statement_id` (→ `not_found`).
- Si `status == 'closed'` → error `already_closed`.
- Contar líneas del extracto con `is_matched=0` (no borradas).
  - Si `> 0` → error `unmatched_lines` con `{unmatched_count:N}` ("Cannot close: N unmatched line(s) remain.").
- Si todas conciliadas: emitir `UPDATE` → `status='closed'`, `updated_by`, `updated_at=now`.
- Devolver `{id, statement_number, status}`.
- Emite `bank_reconciliation.statement.closed`.

---

## Lógica adicional NO expuesta aún como comando

### Guarda "no añadir líneas a extracto cerrado" (`add_statement_line`)
Origen: `ReconciliationService.add_statement_line` (guarda `if stmt.status == 'closed'`).
El comando Tier 0 `bank_reconciliation.lines.add` (`commands/statement_line_add.sql`) inserta
sin comprobar el estado del extracto. Para replicar fielmente el legacy hay que mover esa
comprobación al runtime/WASM (leer `status` del extracto y rechazar con `invalid_state` si
está `closed`). Pendiente de decidir si se hace en WASM o como invariant del runtime.

### Derivación del `confidence_score` por defecto en match manual (`match_create`)
Origen: `ReconciliationService.create_match` (`1.000` manual / `0.900` auto).
Hoy el `match_create.sql` recibe `confidence_score` del payload (el WC manda 1.0 para manual).
Si se quiere centralizar la regla (manual⇒1.000, auto⇒0.900) en vez de confiar en el cliente,
hacerlo en un handler WASM o invariant. La validación `match_type ∈ {auto,manual}` ya la cubre
el JSON Schema `schemas/match_create.json` (enum).

### `get_statement_summary` (query agregada)
Origen: `ReconciliationService.get_statement_summary`. Devuelve
`{total_lines, matched_count, unmatched_count, statement_balance, matched_amount}` donde
`matched_amount = Σ amount_matched` de los matches de las líneas conciliadas del extracto.
Es **solo lectura** (agregación con JOIN + SUM). Se puede expresar como una query SQL adicional
(GROUP BY sobre `bank_reconciliation_line` LEFT JOIN `bank_reconciliation_match`) sin WASM;
no se ha añadido al contrato por no tener una vista de UI que la consuma todavía. Si se necesita,
es una query Tier 0 más (`queries/statement_summary.sql`, permission `view_recon`), no un handler.
