# leads — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_leads/{models.py,services.py}`. El CRUD plano (alta de
origen) ya está en SQL declarativo Tier 0 (`commands/source_create.sql`) y los listados
en `queries/*.sql`. Lo que sigue es la auto-numeración atómica y las guardas de
transición de estado, que **no** caben en una sola sentencia SQL y deben convertirse
en handlers WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el
> runtime le lee, valida la transición, calcula el nuevo estado/timestamps/notas y
> devuelve *intenciones* (comandos internos `leads._insert_lead` / `leads._set_status`
> a ejecutar) que el runtime valida y persiste en una transacción. `estimated_value`
> se trata como decimal con `quantize(0.01)`.

## Convención de transiciones (todas las funciones que tocan un lead)
1. El runtime lee la fila del lead por `lead_id` (scope `hub_id`, `is_deleted=0`) y se la
   pasa al WASM. Si no existe → el runtime devuelve `not_found` antes de invocar al WASM.
2. El WASM valida `status` actual contra la transición pedida (tabla más abajo). Estado
   inválido → error `invalid_state` (no se emite comando, no se persiste nada).
3. El WASM emite `leads._set_status` con: nuevo `status`, los tres timestamps de hito
   (poniendo el que corresponde a `:now` y dejando los demás con su valor previo),
   `estimated_value` y `notes` (con el rastro textual añadido cuando aplica).
4. El runtime persiste y emite el evento declarado en `module.json`.

| función WASM      | transición permitida desde      | a            | hito que sella     |
|-------------------|---------------------------------|--------------|--------------------|
| `mark_contacted`  | `new`                           | `contacted`  | `contacted_at`     |
| `qualify_lead`    | `contacted`                     | `qualified`  | `qualified_at`     |
| `unqualify_lead`  | cualquiera ≠ converted/lost/unqualified | `unqualified` | —          |
| `convert_lead`    | `qualified`                     | `converted`  | `converted_at`     |
| `mark_lost`       | cualquiera ≠ converted/lost     | `lost`       | —                  |

## 1. `create_lead`  (command `leads.leads.create`)
Origen: `LeadService.create_lead` + `_generate_lead_number`.
- Validar: `first_name` no vacío (ya lo cubre el JSON Schema, revalidar en WASM).
- Parsear `estimated_value` (decimal, default `0.00`) → error `invalid_amount` si no parsea.
- Si `source_id` no vacío: el runtime verifica que el origen existe (scope hub_id); si no →
  error `source_not_found`. (El WASM recibe el flag de existencia, no consulta la BD.)
- Generar `lead_number` atómico → ver pieza 2.
- Emitir `leads._insert_lead` con el payload completo + `lead_number` + `status='new'`.
- Devolver `{id, lead_number, full_name, status}`.

## 2. Auto-número de lead (`_generate_lead_number`)
Origen: `LeadService._generate_lead_number`. Formato `LD-YYYYMMDD-NNNN` (NNNN = secuencia
por hub+día, 4 dígitos, zero-padded).
- El legacy lo derivaba con un `COUNT(*) WHERE lead_number LIKE 'LD-YYYYMMDD-%'` + 1: esto
  tiene **ventana de carrera** (dos altas simultáneas → mismo número). En hub-next se
  resuelve como capacidad del runtime: un **counter atómico** (UPSERT
  `INSERT ... ON CONFLICT DO UPDATE ... RETURNING`, key = `hub_id + 'leads' + día`) invocado
  por el handler, igual que el contador de `quotes`. El WASM solo formatea
  `LD-{YYYYMMDD}-{n:04d}` con el número devuelto. Debe ser atómico en SQLite y Postgres.

## 3. `mark_contacted`  (command `leads.leads.mark_contacted`)
Origen: `LeadService.mark_contacted`.
- Guarda: solo desde `new` (si no → `invalid_state`).
- `_set_status`: `status='contacted'`, `contacted_at=:now`, resto de hitos sin cambio,
  `estimated_value`/`notes` sin cambio.

## 4. `qualify_lead`  (command `leads.leads.qualify`)
Origen: `LeadService.qualify_lead`.
- Guarda: solo desde `contacted` (si no → `invalid_state`).
- Si `estimated_value` viene no vacío: parsear (decimal) → error `invalid_amount` si falla;
  ese valor sustituye al actual. Si viene vacío, se conserva el valor previo.
- `_set_status`: `status='qualified'`, `qualified_at=:now`, `estimated_value` (nuevo o previo).

## 5. `unqualify_lead`  (command `leads.leads.unqualify`)
Origen: `LeadService.unqualify_lead`.
- Guarda: bloqueado si `status ∈ {converted, lost, unqualified}` → `invalid_state`.
- Si `reason` no vacío: componer `notes = (notes + "\n[UNQUALIFIED] " + reason).strip()`
  (append con rastro textual — capacidad de composición de string en el host).
- `_set_status`: `status='unqualified'`, sin tocar timestamps de hito, `notes` actualizado.

## 6. `convert_lead`  (command `leads.leads.convert`)
Origen: `LeadService.convert_lead`.
- Guarda: solo desde `qualified` (si no → `invalid_state`).
- `_set_status`: `status='converted'`, `converted_at=:now`.
- Construir y devolver `customer_payload`:
  `{first_name, last_name, email, phone, company, lead_id, lead_number}` + `opportunity`
  (copia de `opportunity_data` si vino en el payload).
- Emitir `leads.lead.converted` con `customer_payload` adjunto.
- **Cross-módulo**: el módulo `customers` (si está activo) escucha `leads.lead.converted` y
  crea el cliente con ese payload. `leads` **no** importa de customers ni escribe en sus
  tablas — la conversión se propaga por contrato de eventos, no por imports. Por eso
  `depends_on` queda vacío (la conversión es opcional/desacoplada).

## 7. `mark_lost`  (command `leads.leads.mark_lost`)
Origen: `LeadService.mark_lost`.
- Guarda: bloqueado si `status ∈ {converted, lost}` → `invalid_state`.
- Si `reason` no vacío: `notes = (notes + "\n[LOST] " + reason).strip()`.
- `_set_status`: `status='lost'`, sin tocar timestamps de hito, `notes` actualizado.
