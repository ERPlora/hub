# verifactu — lógica para handler Rust→WASM (Tier 2) + capacidades de host (Tier 1)

Fuente legacy: `old_modules/m_verifactu/{models.py,hash_service.py,qr_service.py,
contingency.py,recovery_service.py,aeat_client.py,xml_service.py,events.py,scheduled_tasks.py}`.
El CRUD plano (config, reintento/cancelación de cola) ya está en SQL declarativo Tier 0
(`commands/*.sql`) y las lecturas en `queries/*.sql`. **Toda la lógica fiscal, criptográfica,
de red y por lotes vive aquí** y debe convertirse en un handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`) más algunas capacidades de host.

> Cumplimiento RD 1007/2023 (ES): un VerifactuRecord es **inmutable** una vez emitido. La
> creación va encadenada (hash SHA-256) y atómica por (hub, emisor). VeriFactu es de **solo
> lectura** vía UI; la creación la dispara el evento `invoice.created` (no se edita a mano).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el runtime
> (cola/cadena), calcula y devuelve *intenciones* (filas a insertar/actualizar + eventos a
> emitir) que el runtime valida y persiste en una transacción. Importes con `quantize(0.01)`,
> 2 decimales, punto como separador (formato AEAT `format_amount`).

> ⚠️ Nota de arquitectura (CLAUDE.md hub-next §5.3): `verifactu` es **compliance-critical** y
> es candidato explícito a *first-party native plugin estáticamente enlazado* en vez de
> WASM/Extism (igual que `payroll`). La red TLS-mutua a la AEAT y la firma con certificado
> PKCS#12 pueden exceder lo que el sandbox WASM permite — ver pieza 6/7. Si se elige plugin
> nativo, este documento describe igualmente el contrato de cada función.

---

## 1. `create_record`  (command `verifactu.records.create`, handler WASM `create_record`)
Origen: `HashService.create_record_from_invoice` + `models.VerifactuRecord.calculate_hash`
+ `events._process_invoice_event`. Es la pieza central.

Disparadores:
- Evento público `invoice.created` → `record_type="alta"`.
- Evento público `invoice.cancelled` → `record_type="anulacion"`.
- (También invocable manualmente con el mismo payload.)

Lógica no-CRUD:
1. **Ancla de cadena atómica** (`get_chain_anchor`): el runtime lee la última fila de
   `verifactu_record` por `(hub_id, issuer_nif)` ordenada por `sequence_number DESC` con
   bloqueo (SELECT … FOR UPDATE en Postgres; serialización de escritura en SQLite) para cerrar
   la ventana TOCTOU que duplicaría secuencias. Devuelve `(previous_hash, next_sequence)`.
   - Si no hay filas: `previous_hash = ""`, `next_sequence = 1`, `is_first_record = true`.
2. **Timestamp de generación**: capacidad de host (reloj) — `generation_timestamp` con offset
   horario, formato `FechaHoraHusoGenRegistro` (ver `HashService.format_timestamp`).
3. **Cálculo del hash SHA-256** (`calculate_alta_hash` / `calculate_anulacion_hash`):
   - **alta**: `hash_input =`
     `IDEmisorFactura={issuer_nif}&NumSerieFactura={invoice_number}`
     `&FechaExpedicionFactura={format_date(invoice_date)}&TipoFactura={invoice_type}`
     `&CuotaTotal={format_amount(tax_amount)}&ImporteTotal={format_amount(total_amount)}`
     `&Huella={previous_hash}&FechaHoraHusoGenRegistro={format_timestamp(generation_timestamp)}`
   - **anulacion**: igual pero **sin** `TipoFactura`, `CuotaTotal`, `ImporteTotal`.
   - `record_hash = sha256(hash_input.utf8).hexdigest().upper()`.
   - `format_date` → `DD-MM-YYYY`; `format_amount` → 2 decimales con punto; `format_timestamp`
     → ISO con huso. **Replicar exactamente** estos formatos: cualquier desviación rompe la
     validación de la AEAT y la cadena.
4. **QR** (pieza 4): generar `qr_url` y marcar `qr_generated`.
5. **Intenciones de salida**:
   - Insertar `verifactu_record` con `sequence_number`, `previous_hash`, `record_hash`,
     `is_first_record`, snapshot de la factura, `status='pending'`.
   - Insertar `verifactu_event` (`event_type='record_created'`, severity `info`).
   - Si `config.auto_transmit` está desactivado o el sistema está en contingencia: insertar
     `verifactu_contingencyqueue` (priority NORMAL=2, status `pending`).
   - Emitir `verifactu.record.created`.
- Binds/lectura runtime: `config` (vía query interna `verifactu.config.get`), ancla de cadena,
  reloj. Payload = schema `record_create.json`.

## 2. Snapshot de la factura desde el evento `invoice.created`
Origen: `events._process_invoice_event`.
- El payload del evento trae `invoice_id`, `hub_id`, `invoice_type`, `total`. VeriFactu
  necesita además `issuer_nif`, `issuer_name`, `invoice_number`, `invoice_date`,
  `base_amount`, `tax_rate`, `tax_amount`, `total_amount`, `description`.
- **Cross-módulo**: NO leer las tablas privadas de `invoice`. Resolver el resto del snapshot
  llamando a la **query pública** de invoice (p.ej. `invoice.invoices.get`) a través del
  runtime, o ampliando el payload del evento `invoice.created` para que incluya estos campos.
  El handler recibe ya el snapshot resuelto; nunca hace SELECT a `invoice_*`.

## 3. Validación de la cadena de hash  (command `verifactu.chain.validate`, función `validate_chain`)
Origen: `HashService.validate_hash` + `HashService.validate_chain` + `verify_hash_chain`.
- El runtime lee todos los `verifactu_record` de `(hub_id, issuer_nif)` ordenados por
  `sequence_number ASC` y los pasa al WASM.
- Por cada registro: recalcular su hash (pieza 1.3) y comparar con `record_hash`.
- Verificar el encadenamiento: el primero con `previous_hash=""` o `is_first_record=true`;
  cada siguiente con `previous_hash == record_hash` del anterior.
- Devolver `{valid: bool, first_invalid_index: int|null, first_invalid_id: str|null}`.
- Solo lectura: no inserta nada (opcionalmente emite un `verifactu_event` `chain_error` si falla).

## 4. Generación de QR de verificación AEAT  (Tier 1, capacidad de host de render)
Origen: `qr_service.QRService.generate_verification_url` + `generate_qr_data_uri`.
- URL: `https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?` con params
  `nif`, `numserie` (invoice_number), `fecha` (`DD-MM-YYYY`), `importe` (`format_amount(total)`),
  url-encoded. Esto es puro string → puede ir en el WASM (pieza 1.4).
- El **PNG/data-URI** del QR (`generate_qr_code_base64`) requiere la lib `qrcode` →
  **capacidad de host de render** (Tier 1), no WASM. El handler devuelve solo `qr_url`; el
  host renderiza la imagen bajo demanda en la vista de detalle.

## 5. Backoff exponencial de la cola  (parte de pieza 7; origen `models.ContingencyQueue.schedule_retry`)
Origen: `ContingencyQueue.schedule_retry`.
- `attempts += 1`; `last_attempt_at = now`.
- `backoff_minutes = min(interval_minutes * 2**(attempts-1), 60)` → secuencia 5,10,20,40,60(cap).
- `next_attempt_at = now + backoff_minutes`; `status='retrying'`.
- Cálculo puro → WASM. El reintento/cancelación *manual simple* ya está en SQL
  (`commands/contingency_retry.sql`, `contingency_cancel.sql`); esto es el cálculo del backoff
  automático que usa `process_contingency_queue`.

## 6. Transmisión a la AEAT  (command `verifactu.records.transmit`, función `transmit_record`)
Origen: `aeat_client.py` (SOAP), `xml_service.py` (XML), `models.VerifactuConfig` (cert/env).
**Lógica más pesada — candidata a plugin nativo (red + TLS mutua + firma).**
1. Construir el XML del registro (`xml_service`): sobre SOAP con los campos del registro +
   identificación de software (`software_name/id/version/nif`) + huella.
2. Firmar con el certificado PKCS#12 (`certificate_path` + `certificate_password` descifrado
   por el runtime). XAdES / firma del SOAP.
3. POST al endpoint según `environment`:
   - production: `https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/`
   - testing: `https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/`
   - TLS **mutua** (cliente presenta el certificado). → **capacidad de host `http.fetch`
     mediada** + acceso al certificado; el WASM puro no abre sockets TLS.
4. Parsear la respuesta: `aeat_response_code`, `aeat_response_message`, `aeat_csv`.
5. **Intenciones**:
   - UPDATE del `verifactu_record`: `status` (`accepted|rejected|error`),
     `transmission_timestamp`, `aeat_response_code/message`, `aeat_csv`.
   - INSERT `verifactu_event` (`transmission_attempt` + `transmission_success`/`_failure`).
   - Si falla por conexión: encolar/actualizar `verifactu_contingencyqueue` (pieza 5/7) y emitir
     `contingency_start`.
   - Emitir `verifactu.record.transmitted`.
- Solo `verifactu.transmit_verifactu`.

## 7. Procesado por lotes de la cola  (command `verifactu.contingency.process`, función `process_contingency_queue`)
Origen: `contingency.ContingencyManager.process_queue` + `scheduled_tasks.process_contingency_queue`.
Tarea programada **cada 5 min** (`*/5 * * * *`) y trigger manual desde la vista.
- El runtime lee las entradas `status IN ('pending','retrying')` ordenadas por
  `priority ASC, queued_at ASC`, limit `:limit`.
- Por cada entrada cuyo `next_attempt_at <= now`: invocar la transmisión (pieza 6).
  - Éxito → `record_success`: marcar entrada `status` resuelto (o soft-delete/quitar de cola),
    volver a modo NORMAL.
  - Fallo → `record_failure`: aplicar backoff (pieza 5); si `attempts > config.max_retries`
    → `status='failed'` + `verifactu_event` `error`.
- Devolver `{successful: N, failed: M}` y emitir `verifactu.contingency.processed`.
- Operación batch sobre N filas con efectos de red → WASM/plugin (no cabe en una sola UPDATE).

## 8. Chequeo de expiración del certificado  (tarea programada, función `check_certificate_expiry`)
Origen: `scheduled_tasks.check_certificate_expiry` + `VerifactuConfig.days_until_certificate_expiry`.
- Tarea programada **diaria 08:00** (`0 8 * * *`).
- Leer `config.certificate_expiry`; `days = (expiry - hoy).days`.
- Si `days <= 30` (o configurable): INSERT `verifactu_event` `certificate_warning`
  (severity `warning` si <30, `critical` si <=7 o ya caducado).
- Cálculo de fechas puro → WASM; el reloj es capacidad de host.

## 9. Recuperación de la cadena de hash  (NO migrado como command — pendiente de decisión)
Origen: `recovery_service.ChainRecoveryService` (`get_chain_status`, `recover_from_aeat`,
`recover_manual`) + routes `/recovery/aeat`, `/recovery/manual`.
- Reconstruye el ancla de la cadena consultando a la AEAT (red + cert, como pieza 6) o
  inyectando un hash manual validado (`validate_hash_format`: 64 hex).
- **No se ha añadido command ni vista** en esta migración porque depende íntegramente de la
  conectividad AEAT (plugin nativo) y de una decisión de producto sobre exponer la
  recuperación manual de cadena (operación sensible de compliance). Documentado aquí para
  cuando se implemente el plugin nativo: funciones `recover_from_aeat(issuer_nif)` y
  `recover_manual(issuer_nif, hash)` devolviendo `{status, recovered_hash, recovered_invoice,
  message}`. Si se implementa, añadir su command + schema + (opcional) vista `erp-verifactu-recovery`.

## 10. Vista dashboard (NO migrada como component)
Origen: `routes.dashboard`. Eran agregados (counts: total/hoy/mes/pendientes + eventos
recientes + queue_count). No se añadió entrada de navegación `dashboard` (regla: sin nav
muerta). Si se quiere, se resuelve con queries de agregación adicionales (`COUNT(*)` por
estado/fecha) + un component `erp-verifactu-dashboard`; los counts simples pueden ser
queries SQL Tier 0, no requieren WASM.

---

### Eventos que el módulo escucha (declarados en `module.json` → `events.listen`)
- `invoice.created`   → `verifactu.records.create` (record_type=alta) — pieza 1/2.
- `invoice.cancelled` → `verifactu.records.create` (record_type=anulacion) — pieza 1/2.

### Eventos que el módulo emite
- `verifactu.record.created`, `verifactu.record.transmitted`, `verifactu.config.changed`,
  `verifactu.contingency.retried`, `verifactu.contingency.cancelled`,
  `verifactu.contingency.processed`.
