# fiscal_germany — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_fiscal_germany/{models.py,services.py}`. El CRUD plano de lectura
(listados, get por id) ya está en SQL declarativo Tier 0 (`queries/*.sql`). Las primitivas de
escritura por fila (`_insert_*` / `_update_*`) también son Tier 0 (`commands/_*.sql`). Lo que sigue
es la lógica fiscal/contable/validación/autonumeración que **no** cabe en una sola sentencia SQL
y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload (ya validado contra el JSON
> Schema) + filas leídas por el runtime (vía las queries `*.get`), calcula y devuelve *intenciones*
> (comandos internos `_insert_*` / `_update_*` a ejecutar con sus binds) que el runtime valida y
> persiste en una transacción. Los importes se manejan como decimales con 2 posiciones
> (`quantize(0.01)`); en el host se serializan como string para evitar pérdida binaria.

## Capacidades del host requeridas
- **Reloj** (`now` ISO-8601, `today` `YYYY-MM-DD`) — para autonumeración y `submission_date`/`generated_at`.
- **Contador atómico por hub+día** — para las secuencias `XR-YYYYMMDD-NNNN` / `ZF-YYYYMMDD-NNNN`
  (ver pieza 8). En legacy era un `COUNT(...) LIKE prefix%`, con ventana de carrera; en hub-next se
  resuelve como capacidad UPSERT del runtime y el WASM solo formatea.
- **Recorrido de tablas contables** para GoBD (pieza 7) — vía queries públicas de otros módulos
  (NO acceso directo a tablas ajenas).

---

## 1. `upsert_config`  (command `fiscal_germany.config.upsert`)
Origen: `DeFiscalService.update_config` + `_is_valid_ust_id`.
- Validar `ust_id` con formato **USt-IdNr alemán**: `DE` + exactamente 9 dígitos (`^DE[0-9]{9}$`).
  El JSON Schema ya lo refuerza, pero el WASM lo revalida (defensa en profundidad) → error `invalid_ust_id`.
- `steuernummer` y `company_name` obligatorios (no vacíos) → `missing_steuernummer` / `missing_name`.
- Leer la config existente del hub vía `fiscal_germany.config.get`:
  - si **no existe** → intención `_insert_config` (genera `new_id`, `xrechnung_environment` por defecto `test`).
  - si **existe** → intención `_update_config` con `config_id` = id leído (preserva `created_*`).
- `leitweg_id_default` opcional: si viene `null`/ausente en update, **no** se sobrescribe el valor previo
  (el legacy sólo lo cambia cuando `leitweg_id_default is not None`). El WASM debe leer el valor actual y
  re-enviarlo si el payload lo omite.
- Devolver `{id, ust_id, steuernummer, leitweg_id_default}`. Emitir `fiscal_germany.config.updated`.

## 2. `create_xrechnung`  (command `fiscal_germany.xrechnung.create`)
Origen: `DeFiscalService.create_xrechnung`.
- Validar `supplier_ust_id` (formato `DE`+9 dígitos) → `invalid_supplier_ust_id`; `customer_leitweg_id`
  no vacío → `missing_leitweg_id`.
- Parsear `total_netto` y `total_steuer` como decimal(2) → `invalid_amount` si no parsean.
- Calcular `total_brutto = netto + steuer` (quantize 0.01). **No** se confía en un brutto del cliente:
  se deriva siempre (esto es el invariant fiscal — ver pieza 9).
- Generar `document_number` atómico `XR-YYYYMMDD-NNNN` (pieza 8, sequence `xrechnung`).
- Intención `_insert_xrechnung` (status inicial `draft`, `xml_content=''`, `validation_errors=NULL`,
  `submission_date=NULL`). Emitir `fiscal_germany.xrechnung.created`.
- Devolver `{id, document_number, status, total_brutto}`.

## 3. `generate_xrechnung_xml`  (command `fiscal_germany.xrechnung.generate_xml`)
Origen: `DeFiscalService.generate_xrechnung_xml`.
- Leer el doc vía `fiscal_germany.xrechnung.get` (`xrechnung_id`) → `not_found` si no existe.
- Componer el sobre **UBL 2.1 / CIUS-XRechnung 2.x** (placeholder en legacy; el real usa un
  serializador dedicado). Campos del sobre actual:
  `CustomizationID = urn:cen.eu:en16931:2017#compliant#urn:xoev-de:kosit:standard:xrechnung_2.3`,
  `ID = document_number`, `IssueDate = today`, `InvoiceTypeCode = 380`,
  `DocumentCurrencyCode = EUR`, `BuyerReference = customer_leitweg_id`,
  `SupplierUstId = supplier_ust_id`, `TaxExclusiveAmount = total_netto`,
  `TaxAmount = total_steuer`, `PayableAmount = total_brutto`.
- **TODO real**: serialización UBL 2.1 completa con líneas de factura, partes (`AccountingSupplierParty`/
  `AccountingCustomerParty`), `TaxTotal` desglosado por tipo, IBAN de pago, y validación contra el
  esquema KoSIT. El XML va escapado (entidades XML). Considerar generar líneas leyendo el módulo
  `invoice`/`sales` vía contrato público (no implementado todavía).
- Intención `_update_xrechnung` (mismo `status`, `xml_content` nuevo; `validation_errors`/`submission_date`
  re-enviados sin cambio). Devolver `{id, document_number, xml_length}`.

## 4. `validate_xrechnung`  (command `fiscal_germany.xrechnung.validate`)
Origen: `DeFiscalService.validate_xrechnung`. **Máquina de estados** — Tier 2 puro.
- Guarda de estado: sólo desde `draft` o `rejected` → `invalid_state` en otro caso.
- Requiere `xml_content` no vacío → `xml_missing` (hay que llamar a `generate_xml` antes).
- Reglas de validación (placeholder legacy; el real corre el validador KoSIT/Schematron CIUS):
  - `total_brutto == total_netto + total_steuer` → si no, issue `totals_mismatch`.
  - `customer_leitweg_id` presente → si no, issue `missing_leitweg_id`.
- Resultado: `validation_errors = lista de issues (JSON) o NULL`; `status = 'rejected'` si hay issues,
  `'validated'` si no. Intención `_update_xrechnung`. Emitir `fiscal_germany.xrechnung.validated`.
- **TODO real**: ejecutar Schematron EN16931 + reglas CIUS-XRechnung; validar BT-fields obligatorios,
  formato de Leitweg-ID, IBAN, fechas. Devolver issues con `rule_id`/`flag` (fatal/warning).

## 5. `submit_xrechnung`  (command `fiscal_germany.xrechnung.submit`)
Origen: `DeFiscalService.submit_xrechnung`. **Máquina de estados**.
- Guarda de estado: sólo desde `validated` → `invalid_state` en otro caso.
- Transicionar a `submitted`; `submission_date = now` (capacidad reloj del host).
- Intención `_update_xrechnung`. Emitir `fiscal_germany.xrechnung.submitted`.
- **TODO real (NO en WASM puro — necesita red, Tier 1 `http.fetch` mediado por el host)**: enrutado
  **PEPPOL** vía Access Point, resolución del `Leitweg-ID` al endpoint del receptor público, firma del
  mensaje y manejo de la respuesta (ACK/NACK) → transicionar a `accepted`/`rejected`. El WASM no abre
  sockets: pide al host una `http.fetch` mediada y procesa la respuesta. La transición `submitted →
  accepted/rejected` se modela como una actualización posterior (webhook/callback PEPPOL) — pendiente.

## 6. `create_zugferd`  (command `fiscal_germany.zugferd.create`)
Origen: `DeFiscalService.create_zugferd`.
- Validar `supplier_ust_id` (`DE`+9 dígitos) → `invalid_supplier_ust_id`; `customer_name` no vacío
  → `missing_customer`; `profile ∈ {basic, comfort, extended}` → `invalid_profile`.
- Parsear `total_netto`/`total_brutto` como decimal(2) → `invalid_amount`.
- Generar `document_number` atómico `ZF-YYYYMMDD-NNNN` (pieza 8, sequence `zugferd`).
- Intención `_insert_zugferd` (`pdf_a3_path=''`, `xml_embedded=''`). Emitir `fiscal_germany.zugferd.created`.
- Devolver `{id, document_number, profile}`.

## 7. `generate_zugferd_pdf`  (command `fiscal_germany.zugferd.generate_pdf`)
Origen: `DeFiscalService.generate_zugferd_pdf`.
- Leer el doc vía `fiscal_germany.zugferd.get` (`zugferd_id`) → `not_found`.
- Componer el XML embebido **CrossIndustryInvoice (Factur-X/ZUGFeRD)** según `profile` (placeholder
  legacy). Campos actuales: `profile`, `ID=document_number`, `SupplierUstId`, `CustomerName`,
  `TaxBasisTotal=total_netto`, `GrandTotal=total_brutto`. `pdf_a3_path = "zugferd/{document_number}.pdf"`.
- **TODO real (Tier 1 — render PDF es capacidad del host, no WASM)**: ensamblar un **PDF/A-3** con el
  XML CII embebido como adjunto (equivalente a factur-x/mustangproject). El nivel de detalle del XML
  depende del `profile` (basic = mínimo EN16931; comfort/extended = más BG/BT). El WASM compone el XML
  y pide al host (capacidad "render PDF/A-3 + embed attachment") la generación binaria y su escritura a
  S3/local; el host devuelve la ruta final. Intención `_update_zugferd` con `xml_embedded` + `pdf_a3_path`.
- Devolver `{id, document_number, pdf_a3_path, xml_length}`.

## 8. Autonumeración atómica (`XR-/ZF-YYYYMMDD-NNNN`)
Origen: `_generate_xrechnung_number` / `_generate_zugferd_number`.
- Secuencia por **hub + día** (NNNN = 4 dígitos, empieza en 0001). Dos secuencias independientes
  (`xrechnung`, `zugferd`).
- El legacy usaba `COUNT(document_number LIKE 'XR-YYYYMMDD-%') + 1` → **ventana de carrera**. En hub-next
  debe ser un **contador UPSERT atómico** del runtime (sin SELECT→INSERT separado), igual que el patrón
  `QuoteCounter` del módulo `quotes`. El WASM solo formatea `XR-{day}-{n:04d}` / `ZF-{day}-{n:04d}` con el
  número devuelto por la capacidad de contador.

## 9. Invariant fiscal: `total_brutto == total_netto + total_steuer`
Origen implícito en `create_xrechnung` (deriva brutto) + regla de `validate_xrechnung`.
- En altas, `total_brutto` se **deriva** (no se acepta del cliente) → consistencia garantizada.
- En validación, se re-comprueba como issue `totals_mismatch` (defensa frente a datos manipulados o
  documentos importados). Declararlo como invariant del runtime (registro de invariantes) para que se
  fuerce dentro del SAVEPOINT antes del commit.

## 10. `generate_gobd_export`  (command `fiscal_germany.gobd.generate`)
Origen: `DeFiscalService.generate_gobd_export`.
- Parsear y validar `period_start`/`period_end` (ISO `YYYY-MM-DD`) → `invalid_date`; ambos obligatorios
  → `missing_period`; `period_end >= period_start` → `invalid_period`.
- Placeholder legacy: registra metadatos `total_records=0`, `audit_zip_path="gobd/{start}_{end}.zip"`,
  `generated_at=now`. Intención `_insert_gobd`. Emitir `fiscal_germany.gobd.generated`.
- **TODO real (Tier 1/2 — batch + render)**: construir un paquete **GoBD** inmutable:
  - Recorrer las tablas contables del periodo **vía contratos públicos** de los módulos `invoice`,
    `sales`, `payments`, `taxes` (queries `*.list` con filtro de fecha) — **PROHIBIDO** leer tablas
    privadas de otros módulos directamente.
  - Generar `index.xml` (descripción GoBD/GDPdU de los ficheros + estructura de columnas) + exportaciones
    CSV/JSON por tabla, empaquetar en ZIP (capacidad de archivo del host), y subir a S3 (`audit_zip_path`).
  - `total_records` = nº real de asientos/registros exportados. El WASM agrega y compone el manifest;
    la escritura ZIP + subida es capacidad del host.
- Devolver `{id, period_start, period_end, total_records, audit_zip_path, meta}`.

---

## Notas de portabilidad / pendientes
- Submission PEPPOL (pieza 5) y render PDF/A-3 (pieza 7) y empaquetado GoBD (pieza 10) requieren
  **capacidades del host** (red mediada, render PDF, archivado ZIP, S3) — NO son WASM puro. El WASM
  prepara payloads/manifests y delega la E/S.
- La generación de XML completa (UBL 2.1 / CII) con líneas de factura requiere leer el documento origen
  de otro módulo (`invoice`/`sales`) por contrato público; hoy el `invoice_ref` es texto libre sin FK.
- `xrechnung_environment` (test/production) de la config debe condicionar el endpoint/Access Point de
  submission cuando se implemente la red real.
