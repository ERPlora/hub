# WASM-TODO — invoice_series (Tier 2)

Lógica de `old_modules/m_invoice_series/services.py` que **NO** es CRUD declarativo
y debe convertirse en un handler Rust→WASM (Extism) más adelante. WASM nunca toca la
BD: recibe el payload + el estado leído por el runtime, devuelve *intenciones* (filas a
escribir/actualizar + eventos) que el runtime valida y ejecuta dentro de una transacción.

Mientras el handler no exista, los commands marcados con `handler.type=wasm` en
`module.json` (`set_default`, `next_number`) quedan inertes (no hay `dist/handler.wasm`).
El resto del módulo (CRUD de series Tier 0) funciona ya en declarativo.

## 1. `get_next_number` — asignador atómico de secuencia  ★ crítico fiscal

`InvoiceSeriesService.get_next_number`. Es el corazón del módulo y NO es expresable
como un único INSERT/UPDATE declarativo seguro:

- Lee la serie con `SELECT ... FOR UPDATE` (serializa asignaciones concurrentes contra
  la misma serie → RD 1007/2023: **sin huecos, sin duplicados**).
- Valida que la serie exista, sea del hub y esté activa (`is_active`).
- Incrementa `current_sequence` en 1 (lectura→cálculo→escritura atómica).
- Renderiza el número con `format_number(next_seq)` (ver pieza 3).
- Inserta una fila en `invoice_series_allocation` con el número renderizado +
  `document_ref`, respetando la unicidad `(series_id, document_number)`.
- Devuelve `{series_id, sequence, document_number, allocation_id}` y emite
  `invoice_series.number.allocated`.

Intenciones que devolverá el handler: 1 UPDATE de `current_sequence` + 1 INSERT de
allocation. El bloqueo/atomicidad lo aporta la transacción del runtime; el handler
solo expresa el cálculo y las intenciones.

## 2. `set_as_default` — invariante "a lo sumo una default por scope"

`InvoiceSeriesService.set_as_default` + helper `_demote_existing_default`. Condicional
y multi-fila, no es un UPDATE plano:

- Valida que la serie esté activa (rechaza marcar default una inactiva).
- Degrada (`is_default=0`) **todas** las series hermanas del mismo
  `(hub_id, country_code, document_type)` excepto la propia.
- Promueve la serie objetivo a `is_default=1`.
- Mantiene la invariante: ≤1 default por `(hub, country_code, document_type)`.

El mismo `_demote_existing_default` se invoca también desde `create_series` cuando
`is_default=True` (en el porte declarativo, `series_create.sql` inserta con el valor
crudo de `is_default` y el degradado de la hermana queda pendiente de este handler;
hasta entonces, crear una serie con `is_default=1` puede dejar dos defaults — la UI
crea con `is_default=0` y delega el marcado al command `set_default`).

## 3. `format_number` — motor de plantilla del número

`InvoiceSeries.format_number` (models.py). Renderiza la plantilla `format` con
placeholders `{prefix}`, `{suffix}`, `{year}`, `{seq}` / `{seq:05d}`, `{code}`,
`{country}`, `{region}`, con *fallback* seguro `"{prefix|code}-{year}-{seq:05d}"` si
la plantilla está malformada. Necesario tanto en `get_next_number` (pieza 1) como en:

## 4. `peek_next_number` — vista previa formateada

`InvoiceSeriesService.peek_next_number`. La query declarativa `series.peek_next`
devuelve `current_sequence + 1` (entero crudo) + la plantilla `format`, pero el
**número formateado** depende del motor de plantilla (pieza 3). Opciones: renderizarlo
en el WC con la plantilla devuelta (preview puramente visual, sin consumir), o exponer
una función WASM pura `peek(format, seq, …) -> string`. No es mutante.

## 5. Validaciones de negocio de `create_series` / `update_series`

Hoy delegadas al JSON Schema (`schemas/series_create.json`, `series_update.json`) y a
los índices SQL:

- `document_type ∈ DOCUMENT_TYPES` → `enum` en el schema.
- `code` único por hub → índice parcial `uq_invoice_series_hub_code` (la violación
  emerge como error de constraint; el legacy devolvía `duplicate_code` con mensaje).
- `fiscal_year` entero → `type:integer` en el schema.
- whitelist de campos editables en update → `additionalProperties:false` + columnas
  fijas en `series_update.sql` (`code`/`current_sequence` excluidos).

Si se quiere paridad exacta de mensajes de error (`duplicate_code`, `missing_prefix`,
`invalid_document_type`, etc.), esa capa de validación amigable iría también en WASM.
