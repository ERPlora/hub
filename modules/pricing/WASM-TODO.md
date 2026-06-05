# pricing — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_pricing/{models.py,services.py}`. El CRUD plano (alta de
lista, alta de item, alta/desactivación de regla) ya está en SQL declarativo Tier 0
(`commands/*.sql`). Lo que sigue es el **motor de pricing**: cálculo de mejor precio,
aplicación de reglas de descuento por prioridad, y la invariante atómica de "una sola
lista default por hub" — lógica que **no** cabe en una sola sentencia SQL y debe
convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas leídas por el
> runtime (vía las queries declaradas), calcula y devuelve *intenciones* (filas a
> insertar/actualizar, o subcomandos `_unset_default` a ejecutar) que el runtime valida y
> persiste en una transacción. Operaciones de solo lectura (`get_price`,
> `calculate_discount`) devuelven el resultado calculado sin escribir nada.
> Todos los importes se calculan en `Decimal`/entero de céntimos con `quantize(0.01, HALF_UP)`
> — nunca en float binario.

## 1. `create_price_list`  (command `pricing.price_lists.create`)
Origen: `PricingService.create_price_list` + invariante "una sola lista default por hub".
Función WASM: `create_price_list`.
- Validar: `code` no vacío; `name` no vacío.
- Validar/parsear `valid_from` / `valid_until` (ISO `YYYY-MM-DD` o vacío → NULL); fecha mal
  formada → error `invalid_date`.
- Unicidad `(hub_id, code)`: el runtime pasa el resultado de `pricing.price_lists.list`
  (o un lookup por code); si ya existe → error `duplicate_code`.
- **Invariante (lo no-CRUD/atómico):** si `is_default = true`, ANTES de insertar hay que
  bajar la marca a la(s) lista(s) default actuales del hub. El handler emite el subcomando
  `pricing._unset_default` (helper SQL ya creado) y luego el INSERT (`commands/price_list_create.sql`)
  con `is_default` tal cual. Ambos deben correr en la **misma transacción** (el runtime abre
  el SAVEPOINT); si el INSERT falla, el flip del default revierte.
- Devolver `{id, code, name, is_default}`.
- **Binds que necesitará:** payload `{code, name, currency, segment, is_default, valid_from,
  valid_until}` + `hub_id`, `new_id`, `current_user_id`, `now` (inyectados por el runtime) +
  las filas existentes para el chequeo de unicidad y de default previo.

## 2. `get_price`  (command `pricing.price_lists.get_price`, solo lectura)
Origen: `PricingService.get_price`. Función WASM: `get_price`.
- Validar: `product_ref` no vacío; parsear `quantity` (Decimal) → error `invalid_quantity`.
- **Selección de listas candidatas (lógica no-SQL-trivial):**
  1. Si llega `price_list_id`: usar **solo** esa lista (activa). `price_list_id` mal formado
     → error `invalid_id`.
  2. Si no, considerar **todas** las listas activas del hub, y si llega `customer_segment`,
     filtrar a las que tengan `segment == customer_segment` **o** `segment IS NULL` (universal).
  - Sin lista candidata → error `no_price_list`.
- **Matching por bracket de cantidad:** de los items de `product_ref` en las listas candidatas,
  quedarse con los que cumplan `min_quantity <= quantity` y (`max_quantity IS NULL` o
  `quantity <= max_quantity`). Sin match → error `no_price`.
- **Mejor precio = el menor `price`** entre los items que matchean (no el de la lista default,
  ni el primero — hay que comparar todos).
- Devolver `{product_ref, price, quantity, price_list_id}` (la lista ganadora).
- **Binds/payload:** payload `{product_ref, quantity, price_list_id?, customer_segment?}` +
  `hub_id`. El runtime debe entregar al WASM dos lecturas: las listas activas candidatas
  (`pricing.price_lists.list`) y los items de `product_ref` dentro de esas listas
  (`pricing.price_lists.items` filtrado por product_ref). El WASM no consulta la BD; solo
  filtra y elige.

## 3. `calculate_discount`  (command `pricing.rules.calculate_discount`, solo lectura)
Origen: `PricingService.calculate_discount`. Función WASM: `calculate_discount`.
- Validar/parsear `amount` (Decimal) → error `invalid_amount`.
- **Resolución de la lista de reglas (3 modos):**
  - `rules = null` → el runtime entrega todas las reglas activas del hub.
  - `rules = [uuid, ...]` (strings) → el runtime entrega solo esas reglas (activas).
  - `rules = [{...}, ...]` (dicts inline) → usar tal cual, sin lookup (preview).
  - Modo mixto permitido (algunos ids + algunos inline): unir ambos conjuntos.
- **Orden de aplicación:** por `priority` ascendente (menor = se aplica antes), desempate por `code`.
- **Aplicación iterativa sobre el running total** (cada regla opera sobre el importe ya
  descontado por las anteriores, no sobre el `amount` original):
  - Filtros de aplicabilidad contra el `running` actual: si `min_amount` y `running < min_amount`
    → saltar; si `max_amount` y `running > max_amount` → saltar.
  - Si `applies_to == "customer_segment"`: solo aplica si `conditions.segment == customer_segment`.
  - Cálculo del `delta` por `rule_type`:
    - `percent`: `delta = running * value / 100`.
    - `fixed`: `delta = value`.
    - `tiered`: de `conditions.tiers = [{min, discount}, ...]`, elegir el mayor `discount`
      cuyo `min <= running`; `conditions.unit` (`percent` por defecto | `fixed`) decide si ese
      valor es porcentaje (`running * t / 100`) o importe fijo.
    - `buy_x_get_y`: `conditions = {buy, get, unit_price, quantity}`;
      `sets = quantity // (buy + get)`, `free_units = sets * get`, `delta = unit_price * free_units`.
    - `rule_type` desconocido → saltar la regla.
  - **Clamp:** `delta < 0 → 0`; `delta > running → running` (nunca deja el total negativo).
  - `delta_q = quantize(delta, 0.01)`; `running = quantize(running - delta_q, 0.01)`; registrar
    en `applied` `{code, rule_type, value, discount_amount, priority}`.
- Devolver `{original_amount, final_amount, total_discount, applied_rules:[...]}`
  (`total_discount = original - final`, todo quantizado a 0.01).
- **Binds/payload:** payload `{amount, rules?, customer_segment?}` + `hub_id`. El runtime
  entrega al WASM las reglas resueltas (todas activas, o las del filtro por id) ya leídas de BD;
  las reglas inline vienen en el propio payload. `conditions` viaja como JSON (string) y el
  WASM lo parsea. Es la pieza con más ramas de lógica → claramente Tier 2, no SQL.

## 4. Invariante "una sola lista default por hub" (transversal)
Origen: comentario de `PriceList` (modelo legacy) + bloque `atomic()` de `create_price_list`.
- No se modela como índice único parcial (no es portable SQLite↔Postgres de forma uniforme).
- Se garantiza en el handler `create_price_list` (§1) vía el flip atómico con `pricing._unset_default`.
- Si en hub-next existe un registro de invariantes del runtime (estilo `@register_invariant`),
  declarar también un check post-commit "como mucho 1 fila con `is_default=1 AND is_deleted=0`
  por `hub_id`" para que cualquier futura ruta de escritura de listas no pueda romperla.
  No bloqueante para el primer corte del handler, pero recomendado.

## 5. Notas de portabilidad de decimales (todas las piezas)
- `price` es `NUMERIC(15,4)`, `value` de regla `NUMERIC(15,4)`, importes de descuento se
  quantizan a 2 decimales (`HALF_UP`). El WASM debe usar aritmética decimal exacta
  (p.ej. crate `rust_decimal`), nunca `f64`, para que el resultado coincida byte a byte entre
  el backend `single` (SQLite) y `cloud` (Postgres).
