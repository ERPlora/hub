# WASM-TODO — online_store (Tier 2 / runtime)

Lógica de `old_modules/m_online_store/services.py` + `models.py` que **no** es CRUD declarativo
puro y debe convertirse en un handler Rust→WASM (Extism) o en una capacidad del runtime. El WASM
**nunca toca la BD**: valida, calcula y devuelve *intenciones* (ejecuta los sub-commands SQL que
el runtime valida y corre dentro de una transacción). Cada función mapea a una entrada `handler`
en `module.json` (sustituyendo el `sql:` Tier 0 cuando la lógica lo exija).

La mayoría del módulo es CRUD Tier 0 (ya portado a `queries/` + `commands/`). Lo que sigue es lo
que **no** encaja en un único SELECT/INSERT/UPDATE declarativo.

## 1. `get_store_config` — get-or-create del singleton  (query `online_store.config.get`)
Fuente: `StoreService.get_store_config`.
Por qué no es Tier 0 puro:
- Es un **get-or-create**: si no existe fila de config para el hub, el legacy **crea una por
  defecto** (`StoreConfig(hub_id=...)`) y la devuelve. Una query de lectura no puede insertar.
- La query `config_get.sql` cubre la lectura (devuelve la fila viva si existe). El **bootstrap**
  (crear la fila por defecto cuando el resultado es vacío) debe hacerlo el runtime/WASM la
  primera vez: invocar `commands/config_create.sql` (pendiente de crear) o garantizarlo en el
  paso de instalación/seed del módulo.
- Invariant de singleton: **a lo sumo una fila viva** (`is_deleted=0`) por hub. No hay índice
  único parcial portado; debe protegerlo el handler (no crear si ya existe).

## 2. `update_store_config` — get-or-create + validación de campos  (command `online_store.config.update`)
Fuente: `StoreService.update_store_config`.
Por qué no es Tier 0 puro:
- **Get-or-create**: si la config no existe, el legacy la crea antes de actualizar. El
  `config_update.sql` Tier 0 actúa por `config_id` y asume que la fila existe (vía
  `config.get`); el handler debe resolver el get-or-create cuando `config_id` no se conoce.
- **Whitelist de campos**: el legacy rechaza claves desconocidas (`unknown_field`). El JSON
  Schema (`additionalProperties:false`) ya cubre esto a nivel de payload.

## 3. `create_product` — parseo de precio + slug único  (command `online_store.products.create`)
Fuente: `StoreService.create_product`.
Por qué (parcialmente) no es Tier 0:
- **Parseo/validación del precio**: el legacy hace `Decimal(str(price))` con error `invalid_price`.
  Debe usarse aritmética decimal de precisión fija (no float) en el handler para casar con el
  legacy. El JSON Schema valida `price` como `number >= 0`; el redondeo a 2 decimales y el
  rechazo de valores no parseables van al handler/runtime.
- **Slug único por hub**: lo garantiza el índice `ix_online_store_product_hub_slug` (violación →
  el runtime traduce a error `duplicate_slug`). El legacy lo pre-comprueba; con el índice basta.
- El INSERT en sí (`commands/product_create.sql`) es Tier 0.

## 4. `update_stock` — validación de stock no negativo  (command `online_store.products.update_stock`)
Fuente: `StoreService.update_stock`.
Por qué no es Tier 0 puro:
- Validación `new_stock >= 0` (entero), error `invalid_stock`. Cubierto por el JSON Schema
  (`integer, minimum:0`). El UPDATE es Tier 0.

## 5. `create_category` — slug único + validación de padre  (command `online_store.categories.create`)
Fuente: `StoreService.create_category`.
Por qué (parcialmente) no es Tier 0:
- **Slug único por hub**: índice `ix_online_store_category_hub_slug`.
- **Validación de `parent_id`**: el legacy comprueba que la categoría padre exista
  (`parent_not_found`). Un INSERT con `NULLIF(:parent_id,'')` + FK `ON DELETE SET NULL` cubre la
  integridad referencial, pero el **mensaje de error explícito** y la comprobación previa van al
  handler/runtime. (Anti-ciclos en la jerarquía self-referential, si se requiere, también.)
- El INSERT (`commands/category_create.sql`) es Tier 0.

## 6. `create_page` — slug único  (command `online_store.pages.create`)
Fuente: `StoreService.create_page`.
- Slug único por hub: índice `ix_online_store_page_hub_slug`. El INSERT es Tier 0.

## Filtros de lectura que el SDK/UI aplica (no son Tier 2)
- `list_products`: filtros `is_published` (bind `-1` = sin filtro) y `search` (ILIKE por nombre)
  ya resueltos en `queries/products_list.sql`. El parámetro legacy `category_id` **no** estaba
  realmente ligado a producto en el modelo (el legacy solo lo "soft-validaba"); se omite hasta
  que exista una tabla de unión producto↔categoría.
- `list_categories` / `list_pages`: filtros opcionales ya en las queries Tier 0.

## Helpers que migran al handler (no son commands propios)
- Parseo de `Decimal` para `price` / `sale_price` / `weight` (precisión fija, 2 dec. precio,
  3 dec. peso) — casar con el legacy.
- Get-or-create del singleton `StoreConfig` (núcleo de §1 y §2).
- Serialización de `images` (lista JSON) — portable Postgres JSONB / SQLite texto JSON.

## Notas
- No hay motores de cálculo fiscal, batch ni contadores atómicos en este módulo (a diferencia de
  credit_notes/taxes): la lógica no-CRUD se reduce a get-or-create del singleton, parseo decimal
  y validaciones de unicidad/referencia. Por eso **no** se hornea `dist/handler.wasm` todavía:
  con índices únicos + JSON Schema, casi todo el módulo opera en Tier 0/1.
- `publish_product` / `unpublish_product` / `publish_page` son UPDATEs Tier 0 (el invariante de
  estado se protege con `WHERE … AND is_deleted = 0`).
- `delete` de producto es **soft-delete** (no existía en el legacy, que borraba duro): coherente
  con el contrato de fila §2.5.
