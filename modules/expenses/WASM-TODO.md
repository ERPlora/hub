# expenses — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_expenses/{models.py,services.py}`. El CRUD plano (alta de
gasto, alta de categoría) ya está en SQL declarativo Tier 0 (`commands/expense_create.sql`,
`commands/category_create.sql`). Las **transiciones de estado** del flujo de aprobación
necesitan validar el estado de origen antes de mutar (un solo `UPDATE` no puede rechazar
condicionalmente con un código de error limpio), así que van a WASM.

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + la fila leída por el
> runtime, valida la guarda de estado y devuelve *intenciones* (la fila a actualizar +
> el evento a emitir) que el runtime persiste en una transacción. El timestamp `approved_at`
> lo aporta la capacidad "reloj" del host (el WASM no tiene reloj propio).

Flujo de estados (de `models.py`, `Expense`):

```
draft ──submit──▶ submitted ──approve──▶ approved
                       │
                       └──reject──▶ rejected
```

`STATUS_LABELS = draft|submitted|approved|rejected`. Solo `submitted` puede aprobarse o
rechazarse; solo `draft` puede enviarse.

## 1. `submit_expense`  (command `expenses.expenses.submit`)
Origen: `ExpenseService.submit_expense` + `Expense.submit`.
- El runtime lee la fila `expenses_expense` por `id` + `hub_id` (no borrada). Si no existe → error `not_found`.
- Guarda de estado: **solo** si `status == 'draft'`. Si no → error `invalid_state`
  (mensaje: "Cannot submit expense from status <status> (only drafts can be submitted)").
- Intención: `UPDATE` → `status = 'submitted'`, `updated_by = current_user_id`, `updated_at = now`.
- Emitir `expenses.expense.submitted` con `{id, status}`.

## 2. `approve_expense`  (command `expenses.expenses.approve`)
Origen: `ExpenseService.approve_expense` + `Expense.approve`.
- El runtime lee la fila. Si no existe → error `not_found`.
- Guarda de estado: **solo** si `status == 'submitted'`. Si no → error `invalid_state`
  (mensaje: "Cannot approve expense from status <status> (only submitted expenses can be approved)").
- Intención: `UPDATE` → `status = 'approved'`, `approved_by = current_user_id`,
  `approved_at = now` (timestamp del host), `updated_by = current_user_id`, `updated_at = now`.
  (En el legacy, si no había user_id se usaba el hub_id como fallback; en hub-next
  `current_user_id` siempre lo inyecta el runtime, así que no hace falta fallback.)
- Emitir `expenses.expense.approved` con `{id, status, approved_by, approved_at}`.

## 3. `reject_expense`  (command `expenses.expenses.reject`)
Origen: `ExpenseService.reject_expense` + `Expense.reject`.
- `reason` obligatorio y no vacío (ya validado por `schemas/expense_reject.json`).
- El runtime lee la fila. Si no existe → error `not_found`.
- Guarda de estado: **solo** si `status == 'submitted'`. Si no → error `invalid_state`
  (mensaje: "Cannot reject expense from status <status> (only submitted expenses can be rejected)").
- Intención: `UPDATE` → `status = 'rejected'`, `rejection_reason = reason`,
  `updated_by = current_user_id`, `updated_at = now`.
- Emitir `expenses.expense.rejected` con `{id, status, rejection_reason}`.

## Notas de portado / validaciones que NO necesitan WASM
- Validación de `amount` no negativo y formato decimal (2 decimales) → la cubre el JSON
  Schema `expense_create.json` (`pattern` numérico). El legacy lo hacía en Python con `Decimal`.
- `expense_date` por defecto a hoy cuando viene vacío → lo resuelve el SDK/UI antes del
  command (el SQL Tier 0 espera la fecha ya resuelta). Si se quisiera centralizar en el
  servidor, sería una capacidad "reloj" del host, no lógica de negocio → no bloqueante.
- Unicidad de `code` de categoría por hub → la garantiza el índice único
  `ix_expenses_category_hub_code` (devuelve IntegrityError que el runtime mapea a
  `duplicate_code`); no requiere WASM.
- Existencia de la categoría al crear un gasto → la garantiza la FK `category_id` +
  la UI (que solo ofrece categorías existentes en el selector).
