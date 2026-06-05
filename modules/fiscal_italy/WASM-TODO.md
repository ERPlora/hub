# fiscal_italy — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_fiscal_italy/{models.py,services.py}`. El único command
que cabe en SQL declarativo Tier 0 es el alta de líneas Esterometro
(`commands/esterometro_entry_create.sql`). Todo lo demás — auto-numeración atómica,
generación de XML FatturaPA 1.2, transiciones de estado SdI con guardas, y la
agregación batch de declaraciones Esterometro — es lógica que **no** cabe en una
sola sentencia SQL y se convierte en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload (validado contra
> su JSON Schema) + los datos que el runtime ya leyó, calcula y devuelve
> *intenciones* (filas a insertar/actualizar, eventos a emitir) que el runtime valida
> y persiste en una transacción. El runtime inyecta `hub_id`, `current_user_id`, `now`
> y `new_id`. Importes en `Decimal` con `quantize(0.01)`.

> Todos los importes (`total_imponibile`, `total_iva`, `total_documento`,
> `total_amount`) son decimales con 2 posiciones. `total_documento` se calcula, no
> se acepta del cliente.

---

## 1. `config_upsert`  (command `fiscal_italy.config.upsert`)
Origen: `ItFiscalService.update_config`.
- Validar (más allá del schema): `partita_iva` exactamente 11 dígitos numéricos
  (`isdigit()` + `len==11`); `codice_fiscale` y `company_name` no vacíos;
  `sdi_environment ∈ {test, production}`. El schema (`schemas/config_upsert.json`)
  ya cubre estas reglas — la validación aquí es defensa en profundidad.
- **Upsert de la fila única por hub**: el runtime lee la config existente del hub
  (`fiscal_italy.config.get`). Si no existe → intención `_insert` (status inicial,
  `sdi_credentials_hash=''`, `default_codice_destinatario` del payload o `'0000000'`).
  Si existe → intención `_update` de `partita_iva/codice_fiscale/company_name/
  sdi_environment/default_codice_destinatario` (+ `updated_by/updated_at`).
- Restricción `ix_fiscal_it_cfg_hub_piva` (único hub+partita_iva): al cambiar la
  P.IVA a una ya usada por otra fila del mismo hub, el runtime debe devolver error
  `invalid_piva` (en la práctica solo hay una config por hub).
- Devolver `{id, partita_iva, sdi_environment}`.
- Emite `fiscal_italy.config.updated`.
- Permiso `submit_fatturapa` (no `view`): cambia cómo se autorizan los envíos SdI.

## 2. `fatturapa_create`  (command `fiscal_italy.fatturapa.create`)
Origen: `ItFiscalService.create_fatturapa` + `_generate_fatturapa_number`.
- Validar: `supplier_piva` / `customer_piva` no vacíos; `total_imponibile` y
  `total_iva` parseables a `Decimal` ≥ 0; `customer_codice_destinatario` exactamente
  7 chars (vacío → `'0000000'`).
- **Auto-numeración atómica** `FPA-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día,
  4 dígitos): hoy el legacy hace `COUNT(... LIKE 'FPA-YYYYMMDD-%') + 1`, que tiene
  ventana de carrera. En hub-next resolver con capacidad de contador del runtime
  (UPSERT atómico tipo `quotes`), o un counter `INSERT ... ON CONFLICT DO UPDATE
  RETURNING` por `(hub_id, día)`. El WASM solo formatea `FPA-{YYYYMMDD}-{n:04d}`
  con el número devuelto.
- Calcular `total_documento = total_imponibile + total_iva` (quantize 0.01).
- Intención `_insert` de la cabecera (`status='draft'`, `xml_content=''`,
  `sdi_id=''`, `submission_date=NULL`, `rejection_reason=''`).
- Devolver `{id, document_number, status, total_documento}`.
- Emite `fiscal_italy.fatturapa.created`.

## 3. `fatturapa_generate_xml`  (command `fiscal_italy.fatturapa.generate_xml`)
Origen: `ItFiscalService.generate_fatturapa_xml`.
- El runtime lee el documento por id (scope hub) → si no existe, error `not_found`.
- **Render del XML FatturaPA 1.2** (envelope `FatturaElettronica versione="FPR12"`):
  componer `FatturaElettronicaHeader` (`DatiTrasmissione` con `ProgressivoInvio`=
  `document_number`, `FormatoTrasmissione=FPR12`, `CodiceDestinatario`=
  `customer_codice_destinatario`; `CedentePrestatore/IdFiscaleIVA`=`supplier_piva`;
  `CessionarioCommittente/IdFiscaleIVA`=`customer_piva`) + `FatturaElettronicaBody`
  (`DatiGeneraliDocumento`: `TipoDocumento=TD01`, `Divisa=EUR`, `Data`=hoy,
  `Numero`=`document_number`, `ImportoTotaleDocumento`=`total_documento`;
  `DatiBeniServizi/DatiRiepilogo`: `ImponibileImporto`=`total_imponibile`,
  `Imposta`=`total_iva`).
  > El legacy genera un **placeholder** XML 1.2. La serialización real (esquema XSD
  > completo, escape de entidades, validación) debería plugarse como en `m_verifactu`
  > (un `xml_service` dedicado / capacidad del host de render). Mantener el placeholder
  > hasta tener certificados/XSD de producción.
- Intención `_update` de `xml_content` (+ `updated_by/updated_at`).
- Devolver `{id, document_number, xml_length}`.
- Emite `fiscal_italy.fatturapa.xml_generated`.
- Nota: requiere un "reloj" del host para la fecha `Data` (hoy) → capacidad Tier 1.

## 4. `fatturapa_submit_to_sdi`  (command `fiscal_italy.fatturapa.submit_to_sdi`)
Origen: `ItFiscalService.submit_to_sdi`.
- El runtime lee el documento por id (scope hub) → si no existe, error `not_found`.
- **Guarda de estado**: solo `status == 'draft'` (si no → error `invalid_state`).
- **Guarda de XML**: `xml_content` no vacío (si no → error `xml_missing`, "llama a
  generate_xml primero").
- Transición `draft → uploaded`: set `submission_date = now`,
  `sdi_id = 'PENDING-{document_number}'` (placeholder; la llamada SdI real devolverá
  el `IdentificativoSdI`).
  > La integración SOAP/REST con el SdI (Sistema di Interscambio) está **stubbed**.
  > Cuando se wire-en los certificados de producción, la llamada de red va por una
  > capacidad mediada del host (`http.fetch` Tier 1), nunca desde el WASM directamente.
- Intención `_update` (`status`, `submission_date`, `sdi_id`, `updated_by/updated_at`).
- Devolver `{id, document_number, status, sdi_id}`.
- Emite `fiscal_italy.fatturapa.submitted`.

## 5. `fatturapa_update_sdi_status`  (command `fiscal_italy.fatturapa.update_sdi_status`)
Origen: `ItFiscalService.update_sdi_status`.
- El runtime lee el documento por id (scope hub) → si no existe, error `not_found`.
- Validar `new_status ∈ {delivered, rejected, accepted}` (el schema ya lo restringe).
- **Guarda de estado**: solo si `status ∈ {uploaded, delivered}` (si no →
  error `invalid_state`).
- Aplicar: `status = new_status`; si `rejected` → `rejection_reason = payload o 'unknown'`,
  en cualquier otro caso → `rejection_reason = ''`.
- Intención `_update` (`status`, `rejection_reason`, `updated_by/updated_at`).
- Devolver `{id, document_number, status, rejection_reason}`.
- Emite `fiscal_italy.fatturapa.status_changed`.

## 6. `esterometro_declaration_generate`  (command `fiscal_italy.esterometro.declaration.generate`)
Origen: `ItFiscalService.generate_esterometro_declaration`.
- Validar `period_month ∈ 1..12` (el schema ya lo cubre).
- **Batch / agregación**: el runtime lee las `EsterometroEntry` del hub con
  `period_year == Y AND period_month == M AND status == 'pending'`. Contar → `total_entries`.
- **Reuso de declaración existente** del mismo periodo (índice único
  `ix_fiscal_it_estr_decl_period`):
  - si existe y `submission_status == 'submitted'` → error `already_submitted`.
  - si existe (draft/generated) → `_update`: `total_entries = N`,
    `submission_status = 'generated'`.
  - si no existe → `_insert` (`total_entries = N`, `submission_status = 'generated'`).
- **Flip de líneas**: cada entry incluida pasa `pending → included` (`_update` por fila).
- Operación sobre N filas + cabecera en una sola transacción → WASM (no cabe en una
  sola sentencia; hay que contar, decidir insert/update y actualizar N entries).
- Devolver `{id, period_year, period_month, total_entries, submission_status}`.
- Emite `fiscal_italy.esterometro.declaration.generated`.

## 7. `esterometro_declaration_submit`  (command `fiscal_italy.esterometro.declaration.submit`)
Origen: `ItFiscalService.submit_esterometro_declaration`.
- El runtime lee la declaración por id (scope hub) → si no existe, error `not_found`.
- **Guarda de estado**: solo `submission_status == 'generated'` (si no →
  error `invalid_state`).
- Aplicar: `submission_status = 'submitted'`, `submitted_at = now`.
- **Flip batch**: leer las `EsterometroEntry` del mismo periodo con
  `status == 'included'` y pasarlas a `submitted` (`_update` por fila).
  > La transmisión real al Esterometro (red) está stubbed — ver nota §4 sobre
  > integración SdI / capacidad de red mediada.
- Operación batch sobre N filas + cabecera en una transacción → WASM.
- Devolver `{id, period_year, period_month, submission_status}`.
- Emite `fiscal_italy.esterometro.declaration.submitted`.

---

## Notas de migración / contratos
- **Sin imports cross-módulo.** `invoice_ref`, `supplier_piva` y `customer_piva` son
  campos de texto libres (no FK al módulo `invoice`, que puede no estar activo). Si en
  el futuro se quiere enlazar la factura origen, hacerlo vía query pública de `invoice`
  (`invoice.invoices.get`) o por evento, nunca con SELECT directo a sus tablas.
- **`esterometro_entry_create` es Tier 0** (SQL puro): la validación de enums, país
  ISO-2, mes 1..12 y año ≥ 2000 la hace el JSON Schema; la normalización de
  `counterparty_country` a mayúsculas la hace el SDK/UI antes de enviar.
- **ai_context** (de `old_modules/m_fiscal_italy/ai_context.py`): en hub-next el RAG
  es un campo `module.json`, no un archivo Python. Pendiente migrar el texto descriptivo
  como campo `ai_context` cuando se defina ese bloque del manifest.
