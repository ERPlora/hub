# WASM-TODO — credit_notes (Tier 2)

Lógica de `old_modules/m_credit_notes/services.py` + `models.py` que **no** es CRUD declarativo
puro y debe convertirse en un handler Rust→WASM (Extism). El WASM **nunca toca la BD**: valida,
calcula y devuelve *intenciones* (ejecuta los sub-commands SQL `credit_notes._*` que el runtime
valida y corre dentro de una transacción). Cada función mapea a una entrada `handler` en
`module.json`.

## 1. `create_credit_note`  (command `credit_notes.notes.create`)
Fuente: `CreditNoteService.create_credit_note` + `generate_credit_note_number` + `CreditNoteLine.calculate` + `CreditNote.recalculate_total`.
Por qué no es Tier 0:
- **Generación atómica del número** `CN-YYYYMMDD-NNNN` vía upsert sobre `credit_notes_counter`
  (INSERT … ON CONFLICT(hub_id, day) DO UPDATE SET last_number = last_number + 1 RETURNING).
  Es un contador atómico por (hub, día) — no encaja en un único INSERT declarativo.
- **Batch de líneas**: N líneas en una sola operación, cada una con `line_total = quantity * unit_price`
  (quantize a 2 decimales).
- **Recálculo del total**: `total_amount = Σ line_total` tras insertar las líneas.
- **Validaciones**: `direction ∈ {issued_to_customer, received_from_supplier}`, `counterparty_name`
  obligatorio, `lines` no vacío, cada línea con `description`, parseo de fecha ISO y decimales.
Sub-commands SQL a invocar: `credit_notes._insert_note`, `credit_notes._insert_line` (×N).
Emite: `credit_notes.note.created`.

## 2. `apply_to_invoice`  (command `credit_notes.notes.apply`)
Fuente: `CreditNoteService.apply_to_invoice`.
Por qué no es Tier 0:
- **Validación de crédito restante**: suma `amount_applied` de las aplicaciones vivas, comprueba
  `(already + amount_to_apply) <= total_amount`; si no, error `over_applied` con `remaining`.
- Exige estado `issued`; `amount_to_apply > 0`; `invoice_ref` obligatorio.
- **Transición de estado derivada**: si `applied_amount == total_amount` → status `applied`.
- Mantiene `applied_amount` sincronizado en la cabecera.
Sub-commands SQL: `credit_notes._insert_application`, `credit_notes._set_applied`.
Emite: `credit_notes.note.applied`.

## 3. `unapply`  (command `credit_notes.notes.unapply`)
Fuente: `CreditNoteService.unapply`.
Por qué no es Tier 0:
- Borra (soft-delete) una aplicación y **recalcula** `applied_amount = Σ` aplicaciones restantes.
- **Reversión de estado**: si estaba `applied` y el nuevo total ya no iguala `total_amount` →
  vuelve a `issued`. Rechaza si la nota está `cancelled`.
Sub-commands SQL: `credit_notes._delete_application`, `credit_notes._set_applied`.
Emite: `credit_notes.note.unapplied`.

## 4. `cancel_credit_note`  (command `credit_notes.notes.cancel`)
Fuente: `CreditNoteService.cancel_credit_note`.
Por qué no es Tier 0 (regla de negocio, no solo un UPDATE):
- **Bloqueo por importe aplicado**: rechaza cancelar si `status == applied` y `applied_amount > 0`
  (error `applied_locked` — hay que desaplicar o rectificar primero).
- Rechaza si ya está `cancelled` (`already_cancelled`).
- Si hay `reason`, lo anexa a `notes` (`"\n[CANCELLED] {reason}"`) y fija `reason`.
Sub-command SQL: `credit_notes._set_applied` (reutilizado para fijar status/notes/reason).
Emite: `credit_notes.note.cancelled`.

## Helpers que migran al WASM (no son commands propios)
- `_parse_iso_date`, `_parse_decimal` — parseo/validación de entrada.
- `CreditNoteLine.calculate` — `line_total = quantity * unit_price` (Decimal, 2 decimales).
- `CreditNote.recalculate_total` / `CreditNote.remaining_credit` — agregaciones de líneas/aplicaciones.
- `generate_credit_note_number` — upsert atómico del contador (núcleo del handler `create_credit_note`).

## Notas
- Toda la aritmética monetaria debe usar decimal de precisión fija (no float) para casar con el
  legacy (`Decimal`, quantize a 0.01 / cantidades a 0.001).
- `issue_credit_note` (draft→issued) SÍ es Tier 0 declarativo (`commands/note_issue.sql`): el
  invariante de estado se protege con `WHERE … AND status = 'draft'`.
- Las queries de lectura (list/get/lines/applications/remaining_credit) son Tier 0 declarativas.
