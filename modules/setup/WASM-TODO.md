# setup — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_setup/{services.py,templates/*.py}`. El estado del asistente
(`SetupState`) es un singleton CRUD trivial y ya vive en SQL declarativo Tier 0
(`commands/state_*.sql` + `queries/state_get.sql`). Lo que sigue es **toda** la
orquestación de `apply_template`: instalación de módulos, siembra cross-module de
IVA/categorías/productos, flags operativos e identidad de negocio. **No** cabe en SQL
declarativo (es batch + cross-module + dependiente de un registro de plantillas) y debe
convertirse en un handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD** ni importa de otros módulos. Recibe el
> payload + datos leídos por el runtime, calcula y devuelve *intenciones*: comandos
> públicos a ejecutar (`inventory.products.create`, `taxes.rates.create`, …), módulos a
> instalar (vía el flujo marketplace del runtime) y eventos a emitir. El runtime valida
> permisos/tenant y persiste en una transacción. **PROHIBIDO** que setup escriba directo
> en tablas de `inventory`, `taxes`, `configuration` o `system`: todo va por contrato
> (comandos/queries públicos o eventos).

## 0. El registro de plantillas (REGISTRY) → datos embebidos en el WASM
Origen: `templates/__init__.py` + `templates/_base.py` + `templates/{hairdresser,barbershop,
bar_restaurant,pizzeria,kebab}.py`.
- Cada `Template` es data pura (sin I/O): `key`, `name`, `icon`, `cover_image`,
  `modules: tuple[str]`, `tax_rates: tuple[TaxRate]`, `categories: tuple[Category]`,
  `items: tuple[Item]`, flags `supports_{stock,online_booking,tables,delivery}`, `roles`.
- `TaxRate{name, rate: Decimal, default: bool}`; IVA español reutilizable:
  `IVA_GENERAL 21% (default)`, `IVA_REDUCIDO 10%`, `IVA_SUPERREDUCIDO 4%`.
- `Category{slug, name, image, icon}`; `Item{category(slug), name, price, image,
  tax_rate|None, product_type(physical|service), duration_min}`.
- Portar el REGISTRY a tablas estáticas de datos dentro del WASM (o a un JSON embebido).
  La UI ya tiene un espejo de presentación (solo `key/name/icon`); la verdad operativa
  (módulos/IVA/catálogo) vive aquí.
- Invariante: cada `Item.image` y `Category.image` apunta a un WebP existente bajo
  `blueprints/assets/<sector>/`; el path absoluto es
  `{SETTINGS.blueprints_s3_base}/<sector>/<file>.webp`
  (`https://erplora-storage.s3.eu-west-1.amazonaws.com/blueprints`).

## 1. `apply_template`  (command `setup.template.apply`)
Origen: `services.apply_template`. Punto de entrada único. Recibe el payload de
`schemas/template_apply.json`. Orquesta, en orden, dentro de una transacción:

1. Resolver la plantilla por `template_key` en el REGISTRY → error `unknown_template` si no existe.
2. Marcar `SetupState` en `in_progress` (equivale a ejecutar `setup.state.start` con
   `template_key` + `answers` serializadas). Persistir las respuestas:
   `{stock_control, online_booking, has_tables, has_delivery, business_name,
     business_address, business_tax_id, invites}`.
3. Resolver módulos (pieza 2) e instalarlos (pieza 3).
4. Sembrar IVA (pieza 4).
5. Sembrar catálogo: categorías + productos (pieza 5).
6. Aplicar flag de stock (pieza 6) si `stock_control == false`.
7. Registrar identidad de negocio (pieza 7).
8. Éxito → `setup.state.complete` + emitir `setup.completed`
   `{template_key, modules_installed:[...], categories_created, products_created, tax_rates_created}`.
9. Cualquier excepción → rollback → `setup.state.fail` con `error_message` (truncado a 500)
   + emitir `setup.failed` `{template_key, error}`. La transacción debe deshacer toda
   siembra parcial para que el wizard pueda reintentar el paso.

## 2. Resolución de módulos (`_resolve_modules`)
Origen: `services._resolve_modules`.
- Partir de `template.modules`.
- Si `online_booking` y `template.supports_online_booking` → añadir `online_booking` (si no está).
- Si `has_tables` y `template.supports_tables` → añadir `tables` (si no está).
- Si `has_delivery` y `template.supports_delivery` → añadir `delivery` (si no está).
- Devolver la lista deduplicada conservando el orden.

## 3. Instalación de módulos (`_install_modules`)
Origen: `services._install_modules` (+ `_install_from_catalog` / `runtime.activate`).
- **NO** es SQL: es una capacidad del runtime (flujo marketplace: validar entitlement en
  Cloud, descargar zip de S3, verificar SHA256, aplicar migraciones, registrar, activar —
  ver `ARQUITECTURA.md` §2.2/§4). El WASM solo devuelve la *intención* "instala estos
  module_ids" y el runtime la ejecuta resolviendo `depends_on` (topo-sort).
- Idempotente: omitir los ya instalados para el hub. Devolver solo los nuevos.
- Best-effort en activación: si `activate` falla, dejar el módulo como "installed" y log.
- Cross-module estricto: setup **no** lee la tabla `hub_module`/`system` directamente; el
  runtime informa qué módulos ya están instalados.

## 4. Siembra de IVA (`_seed_tax_classes`)
Origen: `services._seed_tax_classes` (legacy escribía `configuration.TaxClass`; en hub-next
el dueño del IVA es el módulo **`taxes`**).
- Por cada `template.tax_rates`: si no existe un rate con ese % para el hub, crear uno vía
  el comando público **`taxes.rates.create`** (o `taxes.categories.create` + `taxes.rates.create`
  según el contrato de `taxes`). El primer rate con `default=True` es el por defecto.
- Mantener un mapa `{rate% → rate_id}` devuelto por el runtime para cablear los productos
  (pieza 5). Idempotente por `(hub_id, country_code, code)`.
- Convención: país `ES`, `tax_type='vat'`. Nombres del REGISTRY (p.ej. "IVA General 21%").

## 5. Siembra de catálogo (`_seed_catalog`)
Origen: `services._seed_catalog` (dueño = módulo **`inventory`**).
- Por cada `template.categories` (con `order` = índice): crear categoría vía comando público
  **`inventory.categories.create`** con `name/slug/icon/image(=url absoluta blueprints)/order`.
  Guardar `{slug → category_id}` (devuelto por el runtime).
- Por cada `template.items`:
  - Resolver `category_id` por `item.category` (slug); si falta la categoría → log y saltar.
  - `rate = item.tax_rate or template.tax_rates[0].rate`; `tax_id = mapa_iva.get(rate, default)`.
  - `sku = slugify(f"{template.key}-{item.name}")[:100]`. `slugify`: lower, `[^a-z0-9]+`→`-`,
    strip `-`.
  - Crear producto vía **`inventory.products.create`** con
    `name, sku, price, stock=0, product_type, image(url absoluta), tax_class_id=tax_id`,
    vinculando la categoría. Contar `products_created`.
- Devolver `(n_categories, n_products)`.

## 6. Flag de control de stock (`_hide_inventory_menu` + InventoryConfig)
Origen: `services._seed_catalog` (rama `if not stock_control`) + `_hide_inventory_menu`.
- Si `stock_control == false`:
  - Ajustar config de inventario vía comando público de `inventory` (equivalente a
    `allow_negative_stock=True`, `low_stock_alert_enabled=False`). **No** escribir directo
    en `inventory_config`.
  - Ocultar el menú de inventario en el sidebar. Legacy lo hacía marcando
    `HubModule.config.menu_hidden=True` (columna JSON de overrides per-hub del módulo
    `system`). En hub-next eso es una capacidad del runtime ("oculta la nav del módulo X
    para este hub"), no un UPDATE directo a la tabla `system`.

## 7. Identidad de negocio (`_record_business_identity`)
Origen: `services._record_business_identity` (dueño = módulo `configuration`/store).
- Si hay `business_name/business_address/business_tax_id`, persistirlos en el singleton de
  configuración de tienda vía el comando público del módulo dueño (equivalente a actualizar
  `StoreConfig.name/address/tax_id`). Si el singleton aún no existe, no forzar el alta
  (lo inicializa el propio módulo de configuración).

## 8. `skip_setup` (Tier 0 — ya migrado)
Origen: `services.skip_setup` → `commands/state_skip.sql`. No requiere WASM.

## 9. Invitaciones de usuario (`invites`, Tier 1 — pendiente)
Origen: `WizardOptions.invites` (`[{email, role}]`). El legacy las guardaba en `answers`
pero no las procesaba. Si se quiere enviar invitaciones reales, va por el contrato de
usuarios/auth del hub (comando público + envío de email vía capacidad de host `http.fetch`
mediada), **no** desde setup directamente. No bloqueante.
