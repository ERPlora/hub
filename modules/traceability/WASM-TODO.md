# traceability — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_traceability/{models.py,services.py}`. El CRUD plano y las
listas/timeline simples ya están en SQL declarativo Tier 0 (`queries/*.sql`,
`commands/link_document.sql`). Lo que sigue es lógica que **no** cabe en una sola
sentencia SQL (escritura multi-fila atómica, recorrido de grafo, filtrado JSON en memoria)
y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime (vía queries), calcula y devuelve *intenciones* (filas a insertar/actualizar) que
> el runtime valida y persiste en una transacción. La fecha/hora "ahora" la provee el host
> (capacidad reloj); el runtime inyecta `:new_id`, `:hub_id`, `:current_user_id`, `:now`.

## 1. `record_event`  (command `traceability.events.record`)
Origen: `TraceabilityService.record_event`.
Es una escritura **multi-fila atómica**: un `traceability_event` + su `traceability_chain`
en la misma transacción → por eso es WASM y no SQL plano.

- Validar `event_type ∈ {received, produced, transferred, sold, returned, scrapped, recalled}`
  → error `invalid_event_type` (el JSON Schema ya lo enumera; revalidar defensivamente).
- Validar `entity_type ∈ {lot, serial, product}` → error `invalid_entity_type`.
- Validar `entity_ref` no vacío → error `missing_entity_ref`.
- Parsear `quantity` a decimal (acepta str/int/float); inválido → error `invalid_quantity`.
  Por defecto `Decimal("0")`.
- Parsear `occurred_at` (ISO `YYYY-MM-DD` o ISO datetime completo; vacío/None → `now()` del host).
  Inválido → error `invalid_date`.
- Si llega `parent_event_id`, validar que es UUID válido → error `invalid_parent`.
- Emitir intención `_insert_event` (fila de `traceability_event`) con todos los campos;
  `recorded_by` = `:current_user_id` (legacy lo dejaba NULL para eventos de sistema — en
  hub-next el usuario activo lo aporta el runtime).
- Calcular `chain_id = f"{entity_type}:{entity_ref}"`.
- Emitir intención `_insert_chain` (fila de `traceability_chain`) con `chain_id`,
  `parent_event_id` (o NULL) y `event_id` = id del evento recién insertado.
- Emitir evento `traceability.event.recorded`.
- Devolver `{id, event_type, entity_type, entity_ref, chain_id, occurred_at}`.

Helper de soporte (capacidad del runtime, no SQL en el WASM):
- `_insert_event` → INSERT en `traceability_event` (mismos binds que un command Tier 0).
- `_insert_chain` → INSERT en `traceability_chain`.

## 2. `recall_impact`  (command/query `traceability.recall.impact`)
Origen: `TraceabilityService.get_recall_impact`. Es un **recorrido de grafo** (BFS) sobre
la cadena → no expresable en una sola sentencia SQL portable SQLite↔Postgres.

- Construir `chain_id = f"{entity_type}:{entity_ref}"`.
- El runtime lee las entradas de cadena vía query `traceability.chain.list` (bind `:chain_id`)
  y se las pasa al WASM. Si no hay filas → devolver `{entity_type, entity_ref, chain_id,
  downstream_events: [], total: 0}`.
- Raíces = entradas con `parent_event_id IS NULL` (puntos de entrada: `received`/`produced`).
- Descendientes iniciales = entradas con `parent_event_id` no nulo.
- BFS aguas abajo cruzando chain_ids: frontera = raíces ∪ descendientes; el runtime resuelve
  los hijos consultando `traceability_chain` por `parent_event_id IN (frontera)` (capacidad de
  lectura iterativa; expón una query `chain_children` con bind lista si hace falta). Por cada
  hijo no visitado que **no** sea raíz, añadir su `event_id` a `descendants`; seguir hasta
  agotar la frontera. Evitar ciclos con un set `visited`.
- Si no hay descendientes → `downstream_events: []`, `total: 0`.
- El runtime lee los eventos `descendants` (por id, scope hub) ordenados por `occurred_at ASC`
  y el WASM los serializa.
- Devolver `{entity_type, entity_ref, chain_id, downstream_events:[...], total:N}`.

> Nota: el bucle SELECT→expandir frontera es iterativo; en hub-next se modela como varias
> lecturas mediadas por el runtime (el WASM pide la siguiente capa de hijos), nunca como
> acceso directo del WASM a la BD.

## 3. `search_by_metadata`  (query `traceability.events.search_metadata`)
Origen: `TraceabilityService.search_by_metadata`. Filtrado de un campo dentro del blob JSON
`metadata` → se hace en memoria para mantener paridad SQLite↔Postgres (sin operadores JSON).

- Validar `key` no vacío → error `missing_key`.
- El runtime lee un lote acotado de eventos (los más recientes por `occurred_at DESC`,
  `limit * 5` con tope) y se lo pasa al WASM.
- El WASM parsea `metadata` de cada evento y queda con aquellos donde `str(metadata[key]) ==
  str(value)`, hasta `limit` coincidencias.
- Devolver `{events:[...], total:N}`.

## 4. Notas no portadas / no críticas
- El `EVENT_TYPE_LABELS` / `ENTITY_TYPE_LABELS` (etiquetas legibles) eran propiedades de
  presentación en el modelo legacy; en hub-next las resuelve la UI (Web Component), no el WASM.
- `link_to_document` ya está como command Tier 0 (`commands/link_document.sql`); la guarda de
  "evento no encontrado" la aplica el runtime (no requiere WASM).
