# fiscal_romania — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_fiscal_romania/{models.py,services.py}`. El CRUD plano de
lectura (listados, get) ya está en SQL declarativo Tier 0 (`queries/*.sql`), y las
escrituras concretas (insert/update fila a fila) están en helpers SQL internos
(`commands/_*.sql`, prefijo `_` = no expuestos al usuario, invocados solo por el handler).

Lo que sigue es la lógica que **no** cabe en una sola sentencia SQL — auto-numeración
atómica, generación de XML (UBL 2.1 / JPK), guardas de máquina de estados y validación
de formato fiscal — y debe convertirse en handler WASM (`handler/src/lib.rs` →
`dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el
> runtime lee por él, valida/calcula y devuelve *intenciones* (qué comando `_*` ejecutar
> con qué binds) que el runtime valida y persiste en una transacción. Todos los importes
> son decimales con `quantize(0.01)` (formato `Numeric(15,2)` del modelo legacy).

Mapa command → función WASM (ver `module.json`):

| command | función WASM | helper(s) SQL que orquesta | evento |
|---|---|---|---|
| `fiscal_romania.config.update` | `update_config` | `_config_upsert` | `config.updated` |
| `fiscal_romania.efactura.create` | `create_efactura` | `_efactura_insert` | `efactura.created` |
| `fiscal_romania.efactura.generate_xml` | `generate_efactura_xml` | `_efactura_update` | — |
| `fiscal_romania.efactura.submit` | `submit_efactura` | `_efactura_update` | `efactura.submitted` |
| `fiscal_romania.efactura.validate` | `validate_efactura` | `_efactura_update` | `efactura.validated` |
| `fiscal_romania.etransport.create` | `create_etransport` | `_etransport_insert` | `etransport.created` |
| `fiscal_romania.etransport.submit` | `submit_etransport` | `_etransport_update` | `etransport.submitted` |
| `fiscal_romania.jpk.generate` | `generate_jpk` | `_jpk_insert` | `jpk.generated` |

---

## 0. Capacidades del host que el handler necesita
- **Reloj**: `today()` (YYYY-MM-DD) y `now()` (ISO datetime UTC sin tz, como hace el
  legacy con `datetime.now(UTC).replace(tzinfo=None)`). Necesario para auto-número y timestamps.
- **Lectura previa**: el runtime debe pasar al WASM la(s) fila(s) implicadas (config actual,
  e-Factura por id, e-Transport por id) ya filtradas por `hub_id` + `is_deleted=0`. El WASM
  nunca consulta la BD.
- **Contador atómico por hub+día** para la auto-numeración (ver pieza 1). Igual que en `quotes`,
  se resuelve como capacidad del runtime (counter UPSERT, sin ventana SELECT→UPDATE); el WASM
  solo formatea el prefijo y recibe el número de secuencia.

## 1. Auto-numeración de documentos (`EFR-YYYYMMDD-NNNN` / `ETR-YYYYMMDD-NNNN`)
Origen: `RoFiscalService._generate_efactura_number` / `_generate_etransport_number`.
- Formato: `{PREFIX}-{YYYYMMDD}-{NNNN}` con `PREFIX ∈ {EFR, ETR}`, `NNNN` = secuencia por
  hub+día, 4 dígitos rellenados con cero.
- El legacy contaba `LIKE 'EFR-YYYYMMDD-%'` y sumaba 1 — **race condition** bajo concurrencia.
  En hub-next debe ser **atómico** (counter UPSERT del runtime, clave `hub_id + tipo + día`),
  idéntico al patrón del contador de `quotes`. El WASM solo compone la cadena con el número devuelto.

## 2. `update_config`  (command `fiscal_romania.config.update`)
Origen: `RoFiscalService.update_config`.
- Validar formato CIF: debe empezar por `RO` y el resto ser solo dígitos
  (`company_cif.startswith("RO") and company_cif[2:].isdigit()`) → error `invalid_cif`.
  (El JSON Schema ya aplica `^RO[0-9]+$`; el WASM revalida — Rust es la única autoridad.)
- `anaf_environment ∈ {test, production}` → error `invalid_env`. `company_name` no vacío → `missing_name`.
- **Upsert con un solo registro por hub**: el runtime pasa la config actual (o ninguna).
  - Si no existe → generar `new_id` y ejecutar `_config_upsert` con ese `id` (rama INSERT).
  - Si existe → ejecutar `_config_upsert` con el `id` existente (rama UPDATE vía `ON CONFLICT(id)`).
  - Nota: el cambio de `company_cif` debe respetar el índice único `(hub_id, company_cif)`;
    si choca con otra fila, devolver error de conflicto (no romper la transacción en silencio).
- Devolver `{id, company_cif, anaf_environment}`. El `api_key_hash` (SHA256) y
  `last_token_refresh_at` se gestionan en el flujo OAuth de ANAF (fuera de este command).

## 3. `create_efactura`  (command `fiscal_romania.efactura.create`)
Origen: `RoFiscalService.create_efactura`.
- Validar: `supplier_cif`/`customer_cif` no vacíos (`missing_supplier`/`missing_customer`);
  `document_type ∈ {invoice, credit_note}` (`invalid_type`).
- Parsear importes: `total_amount`/`vat_amount` llegan como string → `Decimal`; si fallan →
  error `invalid_amount`. Persistir con `quantize(0.01)`.
- Generar `document_number` con la pieza 1 (prefijo `EFR`).
- Emitir intención `_efactura_insert` (estado inicial `draft`).
- Devolver `{id, document_number, status:'draft'}` y emitir `fiscal_romania.efactura.created`.

## 4. `generate_efactura_xml`  (command `fiscal_romania.efactura.generate_xml`)
Origen: `RoFiscalService.generate_efactura_xml`.
- Runtime pasa la e-Factura por id (404 → error `not found`).
- **Componer el XML UBL 2.1** (placeholder hoy; serialización real va en una pieza dedicada
  estilo `m_verifactu`). Estructura mínima del legacy:
  - `<Invoice>` con namespaces UBL `Invoice-2` + `cbc:CommonBasicComponents-2`.
  - `cbc:ID` = `document_number`; `cbc:IssueDate` = `today()`.
  - `cbc:InvoiceTypeCode` = `380` si `document_type == 'invoice'`, `381` si `credit_note`.
  - `cbc:DocumentCurrencyCode` = `RON`.
  - `cbc:SupplierCif` / `cbc:CustomerCif` / `cbc:TaxAmount` (= `vat_amount`) /
    `cbc:PayableAmount` (= `total_amount`).
- Emitir `_efactura_update` reescribiendo solo `xml_content` (los demás campos van con su valor
  actual, que el runtime ha leído). No cambia el estado.
- Devolver `{id, document_number, xml_length}`.

## 5. `submit_efactura`  (command `fiscal_romania.efactura.submit`)
Origen: `RoFiscalService.submit_efactura`.
- **Guarda de estado**: solo desde `draft` (si no → error `invalid_state`).
- **Precondición**: `xml_content` no vacío (si no → error `xml_missing`, "llama a generate_xml primero").
- Transición → `uploaded`; `submission_date = now()`; `upload_id = "PENDING-{document_number}"`
  (placeholder; la llamada real a la API de ANAF devuelve el identificador y va en pieza 8).
- Emitir `_efactura_update` y `fiscal_romania.efactura.submitted`.
- Devolver `{id, document_number, status, upload_id}`.

## 6. `validate_efactura`  (command `fiscal_romania.efactura.validate`)
Origen: `RoFiscalService.validate_efactura`.
- **Guarda de estado**: solo desde `uploaded` (si no → error `invalid_state`).
- Aplicar el resultado de ANAF (`anaf_response`, default `{validated:true}`):
  - `accepted = bool(response.get("validated", true))`.
  - Si aceptado → `status='validated'`, `error_code=''`.
  - Si no → `status='rejected'`, `error_code = str(response.get("error_code","unknown"))`.
- Persistir `anaf_response` (JSON) vía `_efactura_update`. Emitir `fiscal_romania.efactura.validated`.
- Devolver `{id, document_number, status, error_code}`.

## 7. `create_etransport`  (command `fiscal_romania.etransport.create`)
Origen: `RoFiscalService.create_etransport`.
- Validar: `transport_type ∈ {intra_eu, national, international}` (`invalid_type`);
  `origin_city`/`destination_city` no vacíos (`missing_city`); `vehicle_plate` no vacío
  (`missing_plate`); `goods` lista **no vacía** de dicts (`empty_goods`).
- Parsear `departure_date` (ISO `YYYY-MM-DD` o vacío→NULL) → error `invalid_date`.
- Serializar `goods` a JSON para el bind del helper SQL.
- Generar `document_number` con la pieza 1 (prefijo `ETR`).
- Emitir `_etransport_insert` (estado inicial `draft`).
- Devolver `{id, document_number, status:'draft'}` y emitir `fiscal_romania.etransport.created`.

## 8. `submit_etransport`  (command `fiscal_romania.etransport.submit`)
Origen: `RoFiscalService.submit_etransport`.
- **Guarda de estado**: solo desde `draft` (si no → error `invalid_state`).
- Transición → `submitted`; `submitted_at = now()`; `uit_code = "UIT-{document_number}"`
  (placeholder; la llamada real a ANAF devuelve el código de tránsito UIT — pieza 10).
- Emitir `_etransport_update` y `fiscal_romania.etransport.submitted`.
- Devolver `{id, document_number, status, uit_code}`.

## 9. `generate_jpk`  (command `fiscal_romania.jpk.generate`)
Origen: `RoFiscalService.generate_jpk`.
- Validar: `declaration_type ∈ {D300, D394, D406, SAFT}` (`invalid_type`).
- Parsear `period_start`/`period_end` (ISO) → `invalid_date`; ambos requeridos (`missing_period`);
  `period_end >= period_start` (`invalid_period`).
- `total_amount` = `Decimal(data.get("total_amount","0.00"))` (`invalid_amount` si falla), `quantize(0.01)`.
- **Componer el XML JPK** (placeholder hoy):
  `<JPK type="{type}" from="{start}" to="{end}"><TotalAmount>{total}</TotalAmount></JPK>`.
  La construcción real de cada formato (D300 IVA / D394 informativa / D406 SAFT) es lógica
  contable extensa y va en una pieza dedicada por tipo.
- Emitir `_jpk_insert` (estado `generated`, con XML). Emitir `fiscal_romania.jpk.generated`.
- Devolver `{id, declaration_type, status:'generated', total_amount}`.

## 10. Integración ANAF (pendiente, fuera de Tier 0/2 puro)
El legacy deja **stubbed** toda la red contra ANAF (Agentia Nationala de Administrare
Fiscala): hoy solo se registra el estado local y se generan placeholders (`upload_id`,
`uit_code`, XML). Cuando se cableen los certificados de producción:
- El upload real (SOAP/REST de e-Factura, registro de e-Transport, envío JPK) es una llamada
  de red saliente → **capacidad mediada del host `http.fetch`** (Tier 1), no WASM puro, y
  posiblemente un **plugin nativo de primera parte** por ser compliance-critical (igual que
  `verifactu`/`payroll` en ARQUITECTURA.md §5.3).
- OAuth contra ANAF: refresca el token y actualiza `api_key_hash` + `last_token_refresh_at`
  en la config (command/flujo aparte; el modelo ya tiene las columnas).
- Las respuestas reales de ANAF alimentan `validate_efactura` (pieza 6) en vez del default.
