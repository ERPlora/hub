# olap_cubes — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_olap_cubes/{models.py,services.py}`. El CRUD plano de cubos
(crear/actualizar/desactivar) y la invalidación total de caché ya están en SQL declarativo
Tier 0 (`commands/*.sql`). Lo que sigue es lógica de **agregación in-memory**, de
**contador atómico**, de **caché con TTL/expiración** y de **validación contra la definición
del cubo** que no cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos a
> ejecutar) que el runtime valida y persiste en una transacción. Las aggs numéricas usan
> `Decimal`/enteros con `quantize(0.01)` para round-trip determinista (se serializan como
> string en `result_cells`, igual que el legacy).

## 1. `execute_query`  (command `olap_cubes.query.execute`)
Origen: `OLAPService.execute_query` + helpers `_aggregate_data` / `_aggregate` /
`_coerce_numeric` / `_row_matches_filters`.

Entrada (payload): `{cube_id, dimensions:[str], measures:[str], filters:{}, data:[{...}]}`.
El runtime lee primero el cubo (`olap_cubes.cubes.get`) y se lo pasa al WASM.

Pasos:
1. **Guardas**: `dimensions` debe ser lista; `measures` lista no vacía; el cubo debe existir
   y estar **activo** (si no → error `cube_inactive`).
2. **Construir `measure_aggs`** desde `cube.measures` (`{field: agg}`, `agg` por defecto `sum`).
   Toda `measure` solicitada debe estar definida en el cubo (si no → error `unknown_measure`).
3. **Validar dimensiones**: si el cubo define dimensiones, toda `dimension` solicitada debe
   pertenecer a `cube.dimensions[*].field` (si no → error `unknown_dimension`).
4. **Filtrar** `data` por `filters` (igualdad simple, placeholder — ver `_row_matches_filters`).
5. **Agrupar** por la tupla de `dimensions` (preservando orden de aparición) y, por cada
   medida, aplicar su agg:
   - `count` → nº de filas del grupo.
   - `sum` → Σ de valores numéricos coercibles.
   - `avg` → Σ / nº de valores numéricos.
   - `max` / `min` → extremos.
   - Coerción numérica: `None`/`""`/`bool` → no numérico (se descartan); `int/float/str` →
     `Decimal`. Los `Decimal` se serializan a string en la celda.
   - Sin dimensiones → una única fila gran-total.
6. **Cronometrar** la agregación (`execution_time_ms`).
7. **Generar `query_number`** atómico `OLQ-YYYYMMDD-NNNN` → ver pieza 2.
8. **Persistir** la ejecución (intención de INSERT en `olap_cubes_query`):
   `{query_number, cube_id, dimensions_used, measures_used, filters_applied, result_cells,
     result_count, executed_at=now, executed_by_ref=current_user, execution_time_ms}`.
9. Emitir `olap_cubes.query.executed` y devolver
   `{id, query_number, cube_id, result_count, result_cells, execution_time_ms}`.

## 2. Contador atómico de nº de consulta (`_next_query_number`)
Origen: `OLAPService._next_query_number`. Formato `OLQ-YYYYMMDD-NNNN` (NNNN = secuencia por
hub+día, 4 dígitos). El legacy hacía SELECT…LIKE + max(), con ventana de carrera; en hub-next
debe ser **atómico** (counter UPSERT como capacidad del runtime, sin SELECT→UPDATE). El WASM
solo formatea `OLQ-{day}-{n:04d}` con el número devuelto por el runtime. La "fecha de hoy" es
capacidad de reloj del host (UTC).

## 3. `cache_slice`  (command `olap_cubes.cache.put`)
Origen: `OLAPService.cache_slice`. **Upsert con TTL** sobre `(hub_id, cube_id, slice_key)`:
- Guardas: `slice_key` no vacío; `data` no nula; el cubo debe existir.
- `now` = reloj del host; `expires_at = now + ttl_seconds` (default 3600).
- Si ya existe un slice para `(cube_id, slice_key)`: **reemplazar** `data`, `computed_at=now`,
  `expires_at`, y **resetear `hit_count` a 0** (intención de UPDATE).
- Si no existe: insertar nuevo (intención de INSERT, `hit_count=0`).
- Devolver `{id, cube_id, slice_key, computed_at, expires_at, created}`.
- Es upsert condicional (rama insert/update según existencia previa) → no cabe en un solo
  INSERT/UPDATE portable SQLite↔Postgres con el reset de hit_count; va a WASM.

## 4. `get_cached_slice`  (command `olap_cubes.cache.get`)
Origen: `OLAPService.get_cached_slice`. **Lectura con efecto secundario**:
- Guardas: `cube_id` válido; `slice_key` no vacío.
- El runtime lee el slice por `(cube_id, slice_key)`. Si no existe → `{hit:false, slice:null}`.
- **Expiración perezosa**: si `expires_at <= now` (reloj del host) →
  `{hit:false, slice:null, expired:true}` (no se incrementa hit_count).
- En acierto: **incrementar `hit_count`** (intención de UPDATE) y devolver
  `{hit:true, slice:{...}}`.
- La rama hit/miss/expired + el incremento condicional es lógica de lectura-con-mutación →
  WASM (el SQL declarativo de lectura `slices_list.sql` solo lista, no muta).

## 5. Validación de `create_cube` / `update_cube` (Tier 0 + complemento)
Origen: `OLAPService.create_cube` / `update_cube`. La mayoría se cubre con JSON Schema
(`schemas/cube_create.json`, `cube_update.json`: dims/medidas no vacías, `agg` ∈
sum/avg/count/max/min) + el índice único `ix_olap_cube_hub_code` (unicidad de `code` por hub,
incl. al renombrar). **No** requiere WASM salvo que se quiera un mensaje de error de
duplicado más rico que el del constraint; en ese caso el runtime hace la lectura previa.

## 6. Notas de portabilidad
- Columnas JSON (`dimensions`, `measures`, `filters`, `*_used`, `result_cells`, `data`) se
  guardan como TEXT (JSON serializado) en SQLite; el WASM las recibe ya parseadas por el
  runtime y devuelve intenciones con el JSON re-serializado.
- `invalidate_cube_cache` del legacy borraba en duro; en hub-next es **soft-delete**
  (`commands/cache_invalidate.sql`, Tier 0) por el contrato §2.5 — no necesita WASM.
