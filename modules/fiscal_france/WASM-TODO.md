# fiscal_france — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_fiscal_france/{models.py,services.py}`. El listado y las
transiciones triviales ya están en SQL declarativo Tier 0 (`queries/*.sql`,
`commands/*.sql`). Lo que sigue es lógica de validación / cálculo / serialización /
numeración atómica / máquinas de estado que **no** cabe en una sola sentencia SQL y
debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos que el runtime
> le pasa (filas leídas, contadores), valida/calcula y devuelve *intenciones* (los comandos
> helper `_insert_*` / `_update_*` / `_set_*` a ejecutar, más el `payload` inline a
> devolver al caller). El runtime valida permiso + `hub_id` y persiste en una transacción.
> Importes monetarios: `Decimal` con `quantize(0.01)` (paridad con `Decimal(15,2)` legacy).

## Helpers de validación compartidos (legacy `services.py`)
- `is_valid_siret(s)` → `len==14 && all-digit` (sin Luhn).
- `is_valid_siren(s)` → `len==9 && all-digit`.
- `parse_iso_date(v)` → acepta `None`/`""`/`YYYY-MM-DD`/`date`/`datetime`; usado por FEC.
- Numeración atómica por hub+día (ver pieza 6): equivalente a `_generate_facturx_number`
  / `_generate_chorus_number` (cuentan los existentes con el prefijo del día y suman 1).
  **Riesgo de carrera** SELECT count→INSERT en legacy; en hub-next debe resolverse como
  capacidad de contador atómica del runtime (UPSERT/RETURNING), no recontando filas.

---

## 1. `update_config`  (command `fiscal_france.config.update`)
Origen: `FrFiscalService.update_config`.
- Validar: `siret` presente y `is_valid_siret` (→ error `missing_siret`/`invalid_siret`).
- Validar: `siren` presente y `is_valid_siren` (→ error `missing_siren`/`invalid_siren`).
- Validar: `company_name` no vacío (→ error `missing_name`).
- Validar: `chorus_pro_environment ∈ {qualif, production}` (→ error `invalid_env`).
  (El JSON Schema ya hace defensa en profundidad; el WASM mantiene la verdad de negocio.)
- Leer la config existente del hub (el runtime le pasa la fila de `fiscal_france_config`,
  si hay; es única por hub). Decidir:
  - si no existe → emitir `_insert_config` (binds: `new_id`, `siret`, `siren`,
    `company_name`, `chorus_pro_environment`).
  - si existe → emitir `_update_config` (binds: `config_id`, `siret`, `siren`,
    `company_name`, `chorus_pro_environment`).
- Nota: `chorus_credentials_hash` no se toca aquí (siempre `''` en alta; el set de
  credenciales será un comando aparte cuando se cablee Chorus Pro real). No se persiste
  credencial en claro: solo el SHA256 hex.
- Devolver `{id, siret, siren, chorus_pro_environment}`.

## 2. `create_facturx`  (command `fiscal_france.facturx.create`)
Origen: `FrFiscalService.create_facturx`.
- Validar `supplier_siret`/`customer_siret` con `is_valid_siret`
  (→ `missing_supplier`/`invalid_supplier_siret`/`missing_customer`/`invalid_customer_siret`).
- Parsear `total_amount_ht` y `vat_amount` a Decimal (→ error `invalid_amount` si falla).
- Calcular `total_amount_ttc = ht + vat` (quantize 0.01).
- Generar `document_number` atómico `FX-YYYYMMDD-NNNN` (pieza 6).
- Emitir `_insert_facturx` (binds: `new_id`, `document_number`, `invoice_ref`,
  `supplier_siret`, `customer_siret`, `total_amount_ht`, `vat_amount`, `total_amount_ttc`).
  El estado inicial `draft` y el `xml_zugferd_content=''` los fija el SQL helper.
- Devolver `{id, document_number, status:'draft', total_amount_ttc}`.

## 3. `generate_facturx_xml`  (command `fiscal_france.facturx.generate_xml`)
Origen: `FrFiscalService.generate_facturx_xml`.
- El runtime pasa la fila Factur-X (`facturx_id`). Si no existe → error `not_found`
  ("Factur-X not found").
- **Serializar** el XML UN/CEFACT Cross-Industry Invoice (ZUGFeRD) — esta es la pieza
  pesada que justifica el WASM. Plantilla exacta en legacy `generate_facturx_xml`:
  - Envelope `rsm:CrossIndustryInvoice` con namespaces `rsm`/`ram`/`udt` (CII 100).
  - `rsm:ExchangedDocument`: `ram:ID = document_number`, `ram:TypeCode = 380` (factura
    comercial), `ram:IssueDateTime/udt:DateTimeString format="102"` = `YYYYMMDD` de hoy.
  - `SellerTradeParty`/`BuyerTradeParty` → `SpecifiedLegalOrganization/ram:ID schemeID="0009"`
    = `supplier_siret` / `customer_siret` (0009 = esquema SIRET).
  - `ApplicableHeaderTradeSettlement`: `InvoiceCurrencyCode=EUR`;
    `SpecifiedTradeSettlementHeaderMonetarySummation` con `TaxBasisTotalAmount=total_amount_ht`,
    `TaxTotalAmount currencyID="EUR"=vat_amount`, `GrandTotalAmount=total_amount_ttc`.
  - Escapar XML correctamente (legacy interpola sin escape; el WASM debe XML-escapar los
    campos para no romper el documento). 
  - (Futuro: incrustar el XML en un PDF/A-3 real → `pdf_a3_content`. Hoy queda NULL.)
- Transición de estado: si `status == 'draft'` → `'generated'`; en otro caso conservar el
  actual (binds del helper como `new_status`).
- Emitir `_set_facturx_xml` (binds: `facturx_id`, `xml_zugferd_content`, `new_status`).
- Devolver `{id, document_number, status, xml_length}`.

## 4. `submit_facturx`  (command `fiscal_france.facturx.submit`)
Origen: `FrFiscalService.submit_facturx`.
- El runtime pasa la fila (`facturx_id`). Si no existe → error `not_found`.
- **Guarda de estado**: solo `draft`/`generated` pueden enviarse; si no → error
  `invalid_state` ("Only draft or generated documents can be submitted").
- **Guarda de XML**: si `xml_zugferd_content` está vacío → error `xml_missing`
  ("ZUGFeRD XML not generated yet — call generate_facturx_xml first.").
- Calcular `submission_date = now()` (UTC naive, paridad legacy `datetime.now(UTC).replace(tzinfo=None)`).
- Emitir `_set_facturx_submitted` (binds: `facturx_id`, `submission_date`). El helper
  fija `status='submitted'`.
- Devolver `{id, document_number, status:'submitted'}`.

## 5. `create_chorus_invoice`  (command `fiscal_france.chorus.create`)
Origen: `FrFiscalService.create_chorus_invoice`.
- Validar `recipient_service_code` no vacío (→ error `missing_service_code`).
- Parsear `total_amount` a Decimal (→ error `invalid_amount` si falla).
- Generar `document_number` atómico `CPI-YYYYMMDD-NNNN` (pieza 6).
- Emitir `_insert_chorus` (binds: `new_id`, `document_number`, `invoice_ref`,
  `recipient_service_code`, `total_amount`). Estado inicial `draft`, `upload_id`/
  `anomaly_code` vacíos los fija el SQL helper.
- Devolver `{id, document_number, status:'draft'}`.

> Nota: `submit_chorus_invoice` (draft→uploaded, `upload_id='PENDING-<num>'`) NO necesita
> WASM — es la guarda `status='draft'` en el `WHERE` de `commands/chorus_submit.sql` (Tier 0).
> Cuando se cablee la API real de Chorus Pro (POST → `upload_id` devuelto), pasará a Tier 1
> (`http.fetch` mediado) o a un handler WASM que reciba la respuesta del runtime.

## 6. Numeración atómica por hub+día (`FX-`/`CPI-YYYYMMDD-NNNN`)
Origen: `_generate_facturx_number` / `_generate_chorus_number`.
- Secuencia `NNNN` por hub + día, 4 dígitos. Prefijos `FX-{YYYYMMDD}-` y `CPI-{YYYYMMDD}-`.
- Debe ser **atómico** (sin ventana SELECT count→INSERT) en SQLite y Postgres → resolver
  como capacidad de contador del runtime (UPSERT/RETURNING namespeado por
  `(hub_id, doc_kind, day)`), no recontando filas como hace el legacy. El WASM solo formatea
  `{prefix}{n:04d}` con el número que devuelve el runtime.

## 7. `update_chorus_status`  (command `fiscal_france.chorus.update_status`)
Origen: `FrFiscalService.update_chorus_status`.
- El runtime pasa la fila (`chorus_id`). Si no existe → error `not_found`.
- Validar `new_status ∈ {under_review, accepted, rejected, paid}` (→ error `invalid_status`).
- **Guarda de estado**: si la fila está en `draft` → error `invalid_state`
  ("Cannot update status of a draft Chorus invoice — submit first.").
- Lógica de `anomaly_code`:
  - si `new_status == 'rejected'` → `anomaly_code = anomaly_code_in || 'unknown'`.
  - si `anomaly_code_in` viene dado (no None) → usarlo tal cual.
  - si `new_status ∈ {accepted, paid}` y no viene anomaly → limpiar a `''`.
  - en otro caso conservar (el helper SQL setea siempre el campo, así que el WASM debe
    pasar el valor correcto resuelto, no NULL).
- Emitir `_set_chorus_status` (binds: `chorus_id`, `new_status`, `anomaly_code`).
- Devolver `{id, document_number, status, anomaly_code}`.

## 8. `generate_fec`  (command `fiscal_france.fec.generate`)
Origen: `FrFiscalService.generate_fec`. Export FEC (Fichier des Écritures Comptables).
- Validar `format_type ∈ {csv, xml}` (→ error `invalid_format`).
- Parsear `period_start`/`period_end` con `parse_iso_date` (→ error `invalid_date`);
  ambos requeridos (→ `missing_period`); `period_end >= period_start` (→ `invalid_period`).
- `entries` debe ser lista de dicts (→ error `invalid_entries`).
- **Serializar** el payload (pieza pesada → WASM) sobre las 16 columnas canónicas FEC, en
  este orden exacto: `JournalCode, JournalLib, EcritureNum, EcritureDate, CompteNum,
  CompteLib, PieceRef, PieceDate, EcritureLib, Debit, Credit, EcritureLet, DateLet,
  ValidDate, Montantdevise, Idevise`.
  - `csv`: delimitador `|`, fila de cabecera + una fila por entry; columnas ausentes → `''`;
    columnas extra ignoradas (`extrasaction=ignore`).
  - `xml`: `<FEC from=".." to="..">` con un `<Ecriture>` por entry y un sub-elemento por
    columna (`<Col>valor</Col>`). XML-escapar valores.
- Calcular `total_entries = len(entries)` y `generated_at = now()`.
- Emitir `_insert_fec` (binds: `new_id`, `period_start`, `period_end`, `format_type`,
  `total_entries`). Solo metadatos se persisten; el `payload` NO va a BD.
- Devolver `{id, period_start, period_end, format_type, total_entries, payload}` — el
  `payload` (CSV/XML completo) se devuelve inline al caller para que lo descargue/stream-ee.

---

## Eventos emitidos (declarados en `module.json`, los emite el runtime tras commit)
- `fiscal_france.config.updated`
- `fiscal_france.facturx.created` / `.generated` / `.submitted`
- `fiscal_france.chorus.created` / `.uploaded` (Tier 0 submit) / `.status_changed`
- `fiscal_france.fec.generated`

## Integración Chorus Pro / DGFiP real (pendiente, fuera de Tier 0/2 puro)
- En legacy las llamadas de red a Chorus Pro y DGFiP están **stubbed**. La integración
  real (subida B2G, polling de estado, descarga de anomalías) es Tier 1 (`http.fetch`
  mediado por el host) y necesita los certificados de producción. No bloquea este puerto.
