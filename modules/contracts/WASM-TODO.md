# contracts — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_contracts/{models.py,services.py}`. El CRUD plano y las
transiciones de estado con guard simple (un `WHERE status = '...'`) ya están en SQL
declarativo Tier 0 (`commands/*.sql`). Lo que sigue es lógica de numeración atómica,
batch y rastro textual que **no** cabe en una sola sentencia SQL y debe convertirse en
handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos a
> ejecutar) que el runtime valida y persiste en una transacción. Los importes se manejan
> como decimales con `quantize(0.01)`.

## 1. `create_contract`  (command `contracts.contracts.create`)
Origen: `ContractService.create_contract` + `_generate_contract_number`.
- Validar: `customer_name` no vacío → error `missing_customer`.
- Validar `contract_type ∈ {service, recurring, maintenance, other}` → error `invalid_type`.
- Parsear/validar `start_date` y `end_date` (ISO `YYYY-MM-DD` o vacío → NULL) → error `invalid_date`.
- Parsear/validar `monthly_amount` y `total_amount` (decimal, default '0') → error `invalid_amount`.
- Generar `contract_number` atómico → ver pieza 4 (counter).
- Persistir la cabecera con `status = 'draft'` y emitir `contracts.contract.created`.
- Devolver `{id, contract_number, customer_name, status, contract_type}`.
- Va a WASM (no SQL puro) porque combina validación de enum + parseo de fechas/decimales +
  numeración atómica antes del INSERT.

## 2. `expire_old_contracts`  (command `contracts.contracts.expire_old`, tarea programada)
Origen: `ContractService.expire_old_contracts`.
- Seleccionar contratos con `status IN ('active','suspended')` y `end_date IS NOT NULL`
  y `end_date < hoy` (la fecha "hoy" la aporta el host — capacidad de reloj).
- Marcar cada uno como `expired` y devolver `{expired:N, ids:[...]}`.
- `draft` y los ya `terminated` nunca caducan.
- Operación batch sobre N filas que además debe devolver la lista de IDs afectados y emitir
  un evento por lote (`contracts.contract.expired`) → WASM (no una sola UPDATE: necesitamos
  el recuento + la lista, y la comparación con la fecha del host).

## 3. Rastro textual en `notes` (Tier 1, no crítico)
Origen: `suspend_contract(reason=...)`, `terminate_contract(reason=...)`.
- Hoy las transiciones (`contract_suspend.sql`, `contract_terminate.sql`) cambian el estado
  pero **no** escriben el rastro `[SUSPENDED] reason` / `[TERMINATED] reason` en `notes`.
- Si se quiere conservar ese audit-trail textual con timestamp, moverlo a un handler WASM
  que componga el nuevo `notes` (append con marca temporal del host) y persista el cambio
  junto con la transición de estado. No bloqueante: el guard de estado ya vive en el SQL.

## 4. Contador de nº de contrato (`_generate_contract_number`)
Origen: `ContractService._generate_contract_number`.
- Formato `COR-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4 dígitos, zero-padded).
- En el legacy se deriva contando filas con el prefijo de hoy (`COR-YYYYMMDD-` con `LIKE`);
  esa ventana SELECT→derivar→INSERT no es atómica y debe resolverse como **capacidad de
  counter del runtime** (UPSERT atómico tipo `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`),
  igual que en `m_quotes`. El WASM solo formatea `COR-{day}-{n:04d}` con el número devuelto.

## Notas de lifecycle ya cubiertas en SQL (sin WASM)
Las siguientes transiciones tienen guard de estado en el `WHERE` y NO necesitan WASM
(0 filas afectadas = transición inválida, que el runtime traduce a `invalid_state`):
- `activate`  : draft → active                (`contract_activate.sql`)
- `suspend`   : active → suspended            (`contract_suspend.sql`)
- `resume`    : suspended → active            (`contract_resume.sql`)
- `terminate` : active|suspended → terminated (`contract_terminate.sql`)
- `milestones.add` / `milestones.mark_invoiced` (este último con guard `is_invoiced = 0`
  → 0 filas = `already_invoiced`).
