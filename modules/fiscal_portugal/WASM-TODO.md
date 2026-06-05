# fiscal_portugal — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_fiscal_portugal/{models.py,services.py,routes.py}`. Las lecturas
(`config.get`, `saft.list`, `atcud.list`, `at_comm.list`) ya están en SQL declarativo Tier 0
(`queries/*.sql`). Toda la lógica fiscal/contable que **no** cabe en una sola sentencia SQL
(validación NIF, autonumeración por hub+día, composición ATCUD, encadenado de hash, generación
de XML SAF-T PT / Comunicação, y las máquinas de estado) debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload (validado contra el JSON
> Schema del command) + datos que el runtime ya leyó (p.ej. la config del hub), calcula y
> devuelve *intenciones* (comandos internos `_config_upsert` / `_config_update` / `_saft_insert`
> / `_saft_submit` / `_atcud_insert` / `_at_comm_insert` / `_at_comm_submit` /
> `_at_comm_set_status` a ejecutar con sus binds) que el runtime valida y persiste en una
> transacción. El runtime inyecta `:new_id`, `:hub_id`, `:current_user_id`, `:now`.

## Capacidades del host que necesita el handler
- **Reloj**: fecha/hora actual (`now`) para autonumeración (`YYYYMMDD`), `generated_at`,
  `submitted_at`, `created_at`/`updated_at`.
- **Contador atómico por hub+día**: secuencia `NNNN` de `document_number` (ver §2 y §5). Debe
  ser atómica (sin ventana SELECT→COUNT→INSERT) en SQLite y Postgres. En el legacy se hacía con
  `COUNT(... LIKE 'PREFIX%') + 1` (no atómico, condición de carrera bajo concurrencia) — en
  hub-next se resuelve como capacidad de counter UPSERT del runtime; el WASM solo formatea.
- **Hash**: SHA1 (y a futuro SHA-256) para el encadenado de documentos ATCUD (§4).
- **Lectura previa**: el runtime entrega al WASM la `fiscal_portugal_config` del hub (vía
  `queries/config_get.sql`) para resolver `serie_certification_code` en `assign_atcud` (§4) y,
  cuando aplique, el `document_number` de la fila objetivo en submits (§3, §6).

---

## 1. `update_config`  (command `fiscal_portugal.config.update`)
Origen: `PtFiscalService.update_config`.
- Validar: `nif` requerido y exactamente 9 dígitos (`nif.isdigit() and len==9`) → error `invalid_nif`.
  (El JSON Schema ya aplica `^[0-9]{9}$`; el WASM revalida porque Rust es la única autoridad.)
- Validar: `company_name` no vacío → error `missing_name`.
- Validar: `at_environment ∈ {test, production}` → error `invalid_env`.
- Upsert (la config es **única por hub**): el runtime entrega la config existente (`config.get`).
  - Si no existe → intención `_config_upsert` con todos los campos
    (`at_credentials_hash` y `software_certification_number` quedan en `''`;
    `serie_certification_code = serie_certification_code or ''`).
  - Si existe → intención `_config_update` con `config_id` de la fila; `serie_certification_code`
    solo se actualiza si vino no-nulo en el payload (preservar el valor previo si `null`).
- NOTA seguridad: las credenciales AT **nunca** se persisten en claro — se guarda el digest
  SHA256 (`at_credentials_hash`). Hoy el legacy nunca lo rellena en este endpoint; cuando se
  añada la entrada de credenciales, el hash se calcula en el host (capacidad de hash) y se pasa
  como bind a `_config_upsert`/`_config_update` (no implementado aún).
- Devolver `{id, nif, at_environment}`.

## 2. `generate_saft`  (command `fiscal_portugal.saft.generate`)
Origen: `PtFiscalService.generate_saft` + `_generate_saft_number`.
- Validar: `period_type ∈ {monthly, yearly, audit}` → error `invalid_type`.
- Parsear `period_start` / `period_end` como ISO `YYYY-MM-DD`; ambos requeridos
  (`missing_period`); fecha inválida → `invalid_date`; `period_end < period_start` →
  `invalid_period`.
- `total_invoices = len(invoices_data)`.
- `total_amount = Σ Decimal(inv.total_amount)` sobre `invoices_data` (default `0.00`);
  importe no parseable → error `invalid_amount`. Usar decimal con `quantize(0.01)`.
- **Autonumeración** `document_number = SAFT-YYYYMMDD-NNNN` (hoy = fecha actual del host;
  `NNNN` = secuencia por hub+día — ver capacidad de counter).
- **Generar XML SAF-T PT** (placeholder, esquema `urn:OECD:StandardAuditFile-Tax:PT_1.04_01`):
  envelope `<AuditFile><Header>` con `PeriodType/PeriodStart/PeriodEnd/NumberOfEntries/`
  `TotalDebit(0.00)/TotalCredit(total_amount)` + `<SourceDocuments/>`. La serialización real
  por-línea (de `invoices_data`) es trabajo futuro de un `xml_service` dedicado (como
  m_verifactu); por ahora el cuerpo va vacío.
- Persistir con intención `_saft_insert` (status fijado a `generated`, `generated_at = now`).
- Devolver `{id, document_number, status, total_invoices, total_amount}`.

## 3. `submit_saft`  (command `fiscal_portugal.saft.submit`)
Origen: `PtFiscalService.submit_saft`.
- El runtime entrega la fila `fiscal_portugal_saft` por `saft_id` (scoped a `hub_id`); no existe
  → error `not_found`.
- **Guarda de estado**: solo `generated → submitted` (otro estado → error `invalid_state`).
- Si `xml_content` está vacío → error `xml_missing` (debe haberse llamado `generate_saft` antes).
- Intención `_saft_submit` (status `submitted`, `submitted_at = now`). El UPDATE lleva
  `AND status='generated'` como red de seguridad idempotente.
- Placeholder: la llamada real a la API de la AT (SOAP/REST) se inserta aquí en un follow-up.
- Devolver `{id, document_number, status}`.

## 4. `assign_atcud`  (command `fiscal_portugal.atcud.assign`)
Origen: `PtFiscalService.assign_atcud`.
- Validar: `document_type ∈ {invoice, credit_note, receipt}` → `invalid_type`;
  `document_series_code` requerido (`missing_series`); `document_number` requerido (`missing_number`).
- **Resolver `serie_cert`**: el runtime entrega la config (`config.get`); usar
  `config.serie_certification_code` si existe y no vacío, si no → fallback a `document_series_code`
  (la acción nunca se bloquea por falta de config).
- **Componer ATCUD**: `atcud = f"{serie_cert}-{document_number}"`.
- **Encadenado de hash** (software de facturación certificado PT): si vino `hash_value`,
  `signed = true`, si no `hash_value = ''` y `signed = false`. `hash_method = 'SHA1'`.
  TODO real: el hash debe encadenarse con el del documento anterior de la misma serie
  (`hash(prev_hash + datos_doc)`), usando la capacidad de hash del host y la lectura del último
  ATCUD de esa serie que entregue el runtime. Hoy el legacy solo guarda el `hash_value` recibido.
- Persistir con intención `_atcud_insert`.
- Devolver `{id, atcud, document_type, signed}`.

## 5. `create_at_communication`  (command `fiscal_portugal.at_comm.create`)
Origen: `PtFiscalService.create_at_communication` + `_generate_at_comm_number`.
- Validar: `communication_type ∈ {invoice, transport, inventory}` → `invalid_type`;
  `reference_period` requerido (`missing_period`); `content_data` debe ser objeto (`invalid_content`).
- **Autonumeración** `document_number = ATC-YYYYMMDD-NNNN` (misma capacidad de counter que §2).
- **Generar XML** placeholder: `<ATCommunication type=... period=...><Entries>{len(content_data)}`
  `</Entries></ATCommunication>`. La serialización real por endpoint (faturas / transporte /
  inventario) es trabajo futuro.
- Persistir con intención `_at_comm_insert` (status `draft`, `submission_id = ''`).
- Devolver `{id, document_number, communication_type, status}`.

## 6. `submit_at_communication`  (command `fiscal_portugal.at_comm.submit`)
Origen: `PtFiscalService.submit_at_communication`.
- El runtime entrega la fila por `comm_id` (scoped a `hub_id`); no existe → `not_found`.
- **Guarda de estado**: solo `draft → submitted` (otro → `invalid_state`).
- **Componer `submission_id`** placeholder: `PENDING-{document_number}` (necesita el
  `document_number` de la fila, que entrega el runtime). El valor real lo devuelve la AT.
- Intención `_at_comm_submit` (status `submitted`, `submitted_at = now`, `submission_id`).
- Placeholder: la llamada real a la API de la AT se inserta aquí.
- Devolver `{id, document_number, status, submission_id}`.

## 7. `update_communication_status`  (command `fiscal_portugal.at_comm.set_status`)
Origen: `PtFiscalService.update_communication_status`.
- Validar: `new_status ∈ {submitted, accepted, rejected}` → `invalid_status`.
- El runtime entrega la fila por `comm_id`; no existe → `not_found`.
- **Guarda de estado**: solo se puede actualizar desde `{submitted, accepted, rejected}`
  (p.ej. desde `draft` no → error `invalid_state`). Modela la respuesta de la AT sobre una
  comunicación ya enviada.
- Intención `_at_comm_set_status` (el UPDATE lleva `AND status IN (...)` como red de seguridad).
- Devolver `{id, document_number, status}`.

---

## Notas transversales
- **Integración AT real**: todas las llamadas de red a la Autoridade Tributária e Aduaneira
  (SAF-T submit §3, comunicação submit §6) están **stubbed** en el legacy. La integración real
  (certificados de producción + códigos de certificación de serie) es un follow-up; el módulo
  hoy solo registra el estado local y produce XML placeholder. Cuando llegue, va vía la
  capacidad mediada `http.fetch` del host (Tier 1), **no** desde el WASM directamente.
- **Sin dependencias cross-módulo**: `depends_on=[]`. La referencia a la factura origen
  (`invoice_ref`) es texto libre, **sin FK** al módulo `invoice` (que puede no estar activo en
  un hub). Si en el futuro se quiere enlazar de verdad, se hará vía query pública de `invoice`
  o por evento, nunca por SELECT directo a sus tablas.
- **`events.listen` vacío**: este módulo solo emite (config.updated, saft.generated/submitted,
  atcud.assigned, at_comm.created/submitted/status_changed); no escucha eventos de otros módulos
  por ahora.
