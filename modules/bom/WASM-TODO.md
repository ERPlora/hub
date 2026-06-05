# bom — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_bom/{models.py,services.py}`. El CRUD plano y las
transiciones de estado simples ya están en SQL declarativo Tier 0
(`commands/{bom_create,component_add,bom_approve,bom_mark_obsolete}.sql`). Lo que sigue es
lógica de cálculo / batch / atomicidad / recursión que **no** cabe en una sola sentencia
SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el
> runtime le entrega (BOM raíz, líneas, sub-BOMs leídas en cascada), calcula y devuelve
> *intenciones* (filas a insertar/actualizar, comandos a ejecutar) que el runtime valida y
> persiste en una transacción. Las cantidades usan `Decimal`/entero con `quantize(0.0001)`
> (componentes) — replicar `BOMComponent.effective_quantity`.

## Convenciones de cantidad (compartidas)
- `quantity` y `scrap_pct` son decimales (`Numeric(15,4)` y `Numeric(5,2)` en legacy).
- **Cantidad efectiva por línea** (`BOMComponent.effective_quantity`):
  `effective = quantize(quantity * (1 + scrap_pct/100), 0.0001)`.

---

## 1. `set_as_default`  (command `bom.boms.set_default`)
Origen: `BOMService.set_as_default`. **Multi-fila atómico** → no es un solo UPDATE.
- Leer la BOM destino (`bom_id`, scope `hub_id`). Si no existe → error `not_found`.
- Guarda de estado: si `status == 'obsolete'` → error `invalid_state`
  ("Obsolete BOMs cannot be set as default").
- El runtime entrega también los **hermanos**: todas las BOMs con el mismo `product_ref`
  (mismo hub) que tengan `is_default = 1`.
- Intenciones a devolver (todas en una transacción):
  - Por cada hermano con `id != bom_id`: `UPDATE is_default = 0` (+ `updated_by`/`updated_at`).
  - Para la BOM destino: `UPDATE is_default = 1` (+ `updated_by`/`updated_at`).
- Emitir `bom.bom.default_changed` con `{id, product_ref}`.
- Invariante que el runtime debe garantizar tras commit: **a lo sumo una** `is_default = 1`
  por `(hub_id, product_ref)`.

## 2. `explode_bom`  (command `bom.boms.explode`, solo lectura / cálculo)
Origen: `BOMService.explode_bom` + el walk recursivo `_walk`. **Recursión multinivel** →
no expresable en SQL declarativo de una sentencia.
- Parsear/validar `target_quantity` (decimal). Si `<= 0` → error `invalid_quantity`.
- `max_depth` por defecto 5 (rango 1–20 por schema). Cortar recursión cuando `depth > max_depth`.
- El runtime entrega la BOM raíz y, bajo demanda del walk, las líneas de cada BOM y las
  sub-BOMs referenciadas (`sub_bom_id`), todas scope `hub_id`. El WASM no lee BD: declara
  qué BOM/líneas necesita o el runtime le pasa el subárbol completo (decisión de host).
- Algoritmo (`_walk(current_bom, multiplier, depth)`):
  - Para cada componente de `current_bom`:
    - `effective_qty = effective_quantity(comp) * multiplier`.
    - Si `comp.sub_bom_id` está presente: recursar `_walk(sub, effective_qty, depth+1)`
      (la sub-BOM se ignora si no existe / fue borrada). **No** se emite la sub-BOM como línea.
    - Si es hoja (`sub_bom_id` NULL): acumular en `materials[component_ref]`:
      - primera vez → `{component_ref, unit, quantity: effective_qty, is_optional}`.
      - posteriores → `quantity += effective_qty`; si **alguna** agregación es obligatoria
        (`is_optional == False`), la fila resultante queda obligatoria (`is_optional = False`).
  - Arranque: `_walk(root, target_quantity, depth=1)`.
- Salida: lista `materials` ordenada por `component_ref` ascendente, cada fila con
  `{component_ref, unit, quantity: quantize(0.0001) como string, is_optional}`.
- Devolver `{bom_id, target_quantity, materials, count}`. Operación de solo lectura
  (no persiste nada).
- Nota de seguridad: detectar ciclos / profundidad (un sub_bom que se referencia en cadena)
  — el `max_depth` ya acota, pero conviene cortar también ante repetición de `bom_id` en la pila.

## 3. `clone_bom`  (command `bom.boms.clone`)
Origen: `BOMService.clone_bom`. **Cabecera + N líneas copiadas en una transacción** →
batch, no una sola sentencia.
- Validar `new_code` y `new_version` no vacíos (ya lo cubre el schema; revalidar en runtime).
- Leer BOM origen (`source_bom_id`, scope `hub_id`). Si no existe → error `not_found`.
- Unicidad: si ya existe una BOM con `code == new_code` (mismo hub) → error `duplicate_code`
  (garantía dura: índice `uq_bom_hub_code`).
- Leer las líneas de la BOM origen (scope `hub_id`, no borradas).
- Intenciones (transacción única):
  - Insertar nueva cabecera BOM: `code=new_code`, `name=source.name`,
    `product_ref=source.product_ref`, `version=new_version`, `status='draft'`,
    `is_default=0`, `notes=source.notes`. (Nunca default: se promueve después con `set_default`.)
  - Por cada línea origen, insertar una copia apuntando al nuevo `bom_id`
    (`component_ref, quantity, unit, scrap_pct, is_optional, sub_bom_id` tal cual).
- Emitir `bom.bom.cloned` con `{id, source_bom_id, code, version, components_copied}`.
- Devolver `{id, source_bom_id, code, version, status, components_copied}`.

## 4. Rastro textual del motivo en `mark_obsolete` (Tier 1, no crítico)
Origen: `BOMService.mark_obsolete(reason=...)`.
- El SQL Tier 0 (`bom_mark_obsolete.sql`) cambia el estado pero **no** anexa
  `\n[OBSOLETE] {reason}` a `notes`.
- Si se quiere conservar ese audit-trail textual, moverlo a un handler WASM que recomponga
  `notes` (append) usando la capacidad de "reloj" del host. No bloqueante.

## 5. Guardas de validación que el runtime aplica antes de los commands Tier 0
Documentadas aquí para no perderlas (no requieren WASM, son validación de payload/estado):
- `create_bom`: `code`/`name`/`product_ref` no vacíos; `code` único por hub (índice).
- `add_component`: `component_ref` no vacío; `quantity > 0`; si `sub_bom_id` se pasa, debe
  existir (scope hub) y **no** puede ser la propia BOM (`self_reference`).
- `approve_bom`: solo desde `draft` (el `WHERE status='draft'` lo fuerza; el runtime debe
  devolver error `invalid_state` si 0 filas afectadas).
- `mark_obsolete`: error `already_obsolete` si ya estaba obsolete (0 filas afectadas).
