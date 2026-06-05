# sepa_remittances — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_sepa_remittances/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0:

- `commands/mandate_create.sql` — alta de mandato (unicidad por índice).
- `commands/mandate_revoke.sql` — `active → revoked` (guard de estado en el `WHERE status='active'`).
- `commands/remittance_mark_sent.sql` — `generated → sent` (guard `WHERE status='generated'`).

Lo que sigue es lógica de **batch / cálculo / contador atómico / generación de XML** que **no**
cabe en una sola sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` →
`dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el runtime,
> calcula y devuelve *intenciones* (filas a insertar/actualizar vía los comandos helper
> `_insert_line` / `_update_remittance_state` / `_set_line_status`) que el runtime valida y
> persiste en una transacción. Importes con `quantize(0.01)` (Numeric(15,2)).

## Comandos helper (Tier 0, invocados solo por el WASM — no desde la UI)
- `sepa_remittances._insert_line` (`commands/_insert_line.sql`) — inserta una línea ya validada
  (`status='pending'`). Binds: `new_id, hub_id, remittance_id, mandate_id (NULL en transferencia),
  counterparty_name, counterparty_iban, amount, concept, end_to_end_id, current_user_id, now`.
- `sepa_remittances._update_remittance_state` (`commands/_update_remittance_state.sql`) — persiste
  cabecera (status, total_amount, total_count, xml_content, generated_at, notes). Binds:
  `remittance_id, hub_id, status, total_amount, total_count, xml_content, generated_at, notes,
  current_user_id, now`.
- `sepa_remittances._set_line_status` (`commands/_set_line_status.sql`) — fija `status` +
  `rejection_reason` de una línea. Binds: `line_id, hub_id, status, rejection_reason,
  current_user_id, now`.

## 0. Contador atómico `remittance_id` (`generate_remittance_id`)
Origen: `RemittanceCounter` + `generate_remittance_id` (UPSERT `INSERT ... ON CONFLICT DO UPDATE
... RETURNING`). Formato `SEPA-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4 dígitos).
- Debe ser atómico (sin ventana SELECT→UPDATE) en SQLite y Postgres. Tabla `sepa_remittances_counter`
  (índice único `(hub_id, day)`).
- En hub-next se resuelve como **capacidad del runtime** (counter UPSERT) invocada por el handler;
  el WASM solo formatea `SEPA-{day}-{n:04d}` con el número devuelto.
- Guard adicional: índice único `(hub_id, remittance_id)` en `sepa_remittances_remittance`.

## 1. `create_direct_debit`  (command `sepa_remittances.remittances.create_direct_debit`)
Origen: `SepaService.create_direct_debit`.
- Validar/parsear `execution_date` (ISO `YYYY-MM-DD`; requerido). Validar `lines` no vacía.
- Generar `remittance_id` atómico → pieza 0.
- Crear cabecera `remittance_type='direct_debit'`, `status='draft'`, `currency` (default 'EUR').
- Por cada línea (idx desde 1):
  - `mandate_id` **requerido** → el runtime lo lee de `sepa_remittances_mandate` (query interna)
    y el WASM verifica que **existe y `status='active'`** (si no → error `inactive_mandate` /
    `mandate_not_found`). El WASM no consulta la BD: el runtime le entrega los mandatos resueltos.
  - `amount` debe ser `> 0` (error `invalid_amount`).
  - `counterparty_name` / `counterparty_iban` por defecto = `debtor_name` / `debtor_iban` del mandato.
  - `end_to_end_id` por defecto = `f"{remittance_ref}-{idx:04d}"`.
  - Emitir `_insert_line` (con `mandate_id` resuelto = id de fila del mandato).
- Recalcular totales (pieza 3) y `_update_remittance_state` (status='draft', generated_at=NULL,
  notes del payload).
- Devolver `{id, remittance_id, remittance_type, status, total_amount, total_count}`.

## 2. `create_credit_transfer`  (command `sepa_remittances.remittances.create_credit_transfer`)
Origen: `SepaService.create_credit_transfer`.
- Igual que la pieza 1 pero **sin mandato** (`mandate_id` siempre NULL en `_insert_line`).
- Por cada línea: `counterparty_name` y `counterparty_iban` **requeridos**; `amount > 0`.
- `end_to_end_id` por defecto = `f"{remittance_ref}-{idx:04d}"`.
- `remittance_type='credit_transfer'`, `status='draft'`. Totales (pieza 3) + `_update_remittance_state`.

## 3. Recálculo de totales (`recalculate_totals`)
Origen: `Remittance.recalculate_totals`.
- `total_amount = quantize(Σ line.amount, 0.01)`.
- `total_count = nº de líneas`.

## 4. `generate_xml`  (command `sepa_remittances.remittances.generate_xml`)
Origen: `SepaService.generate_xml` + `_build_direct_debit_xml` / `_build_credit_transfer_xml`.
Aquí va **toda la lógica de generación del fichero SEPA** — es el grueso del WASM.
- Guard de estado: **solo** desde `status='draft'` (si no → error `invalid_state`).
- El runtime entrega las líneas de la remesa; si no hay líneas → error `empty_remittance`.
- Recalcular totales antes de serializar la cabecera (pieza 3).
- **Direct debit → pain.008** (`urn:iso:std:iso:20022:tech:xsd:pain.008.001.02`):
  - `CstmrDrctDbtInitn` con `GrpHdr` (`MsgId=remittance_id`, `CreDtTm`=reloj del host,
    `NbOfTxs=total_count`, `CtrlSum=total_amount`).
  - `PmtInf` (`PmtMtd=DD`, `ReqdColltnDt=execution_date`).
  - Por línea `DrctDbtTxInf`: `EndToEndId`, `InstdAmt Ccy=currency`, `MndtRltdInf/MndtId`
    (= `mandate.mandate_id`, el UMR; el runtime lo resuelve a partir del `mandate_id` de fila),
    `Dbtr/Nm`, `DbtrAcct/IBAN`, `RmtInf/Ustrd=concept`.
- **Credit transfer → pain.001** (`urn:iso:std:iso:20022:tech:xsd:pain.001.001.03`):
  - `CstmrCdtTrfInitn` con `GrpHdr` análogo; `PmtInf` (`PmtMtd=TRF`, `ReqdExctnDt=execution_date`).
  - Por línea `CdtTrfTxInf`: `EndToEndId`, `Amt/InstdAmt Ccy=currency`, `Cdtr/Nm`,
    `CdtrAcct/IBAN`, `RmtInf/Ustrd=concept`.
- **Escapado XML** de todos los valores de texto (`& < > " '`).
- Persistir vía `_update_remittance_state`: `xml_content=<xml>`, `status='generated'`,
  `generated_at=`reloj del host, totales recalculados.
- Devolver `{id, remittance_id, status, total_count, total_amount, xml_length}`.
- **Nota de producción**: el legacy es un placeholder pain.008/pain.001 no bit-perfect. La versión
  real debería usar una librería SEPA / validar contra el XSD ISO 20022. Esa validación de esquema
  es una capacidad de host (Tier 1) o lógica WASM adicional, no SQL.

## 5. `mark_processed`  (command `sepa_remittances.remittances.mark_processed`)
Origen: `SepaService.mark_processed`.
- Guard de estado: **solo** desde `status='sent'` (si no → error `invalid_state`).
- El runtime entrega las líneas; el WASM construye el mapa `line_id → línea`.
- Si `processed_lines` viene:
  - Validar cada `line_id` (error `line_not_found` si desconocido).
  - `status ∈ {processed, rejected}` (error `invalid_line_status`); si `rejected`, fijar
    `rejection_reason`. Emitir `_set_line_status` por línea.
- Si `processed_lines` vacío/omitido → marcar **todas** las líneas `processed` (`_set_line_status`).
- Transicionar cabecera a `processed` (`_update_remittance_state`, conservando totales/xml/notes).
- Devolver `{id, remittance_id, status, lines_count}`.
- Es batch sobre N líneas con validación cruzada → WASM (no una sola UPDATE).

## 6. `mark_rejected`  (command `sepa_remittances.remittances.mark_rejected`)
Origen: `SepaService.mark_rejected`.
- `reason` requerido (error `missing_reason`).
- Guard de estado: solo desde `status ∈ {sent, generated}` (si no → error `invalid_state`).
- Si `rejected_lines` viene: marcar esas líneas `rejected` con su `rejection_reason`
  (default = `reason`); el resto se deja intacto. Validar `line_id` (error `line_not_found`).
- Si omitido → todas las líneas `rejected` compartiendo `reason`. Emitir `_set_line_status` por línea.
- Cabecera → `rejected`; **append** a `notes`: `f"{notes}\n[REJECTED] {reason}".strip()`
  (el host aporta el texto/timestamp). `_update_remittance_state`.
- Devolver `{id, remittance_id, status, reason}`.

## 7. Append de motivo en `revoke_mandate` (Tier 1, no bloqueante)
Origen: `SepaService.revoke_mandate(reason=...)`.
- `commands/mandate_revoke.sql` hace la transición `active → revoked` + `revoked_at` pero **no**
  appenda `\n[REVOKED] {reason}` a `notes`.
- Si se quiere conservar ese rastro textual, moverlo a un handler WASM que componga el nuevo
  `notes`. No bloqueante (la revocación funciona sin ello).
