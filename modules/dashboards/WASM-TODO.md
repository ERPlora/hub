# dashboards — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_dashboards/{models.py,services.py}`. El CRUD plano de
paneles, widgets y comparticiones ya está en SQL declarativo Tier 0 (`commands/*.sql`).
Lo que sigue es lógica que **no** cabe en una sola sentencia SQL (read-then-branch,
copia en lote) y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos que el runtime
> le precarga, calcula y devuelve *intenciones* (filas a insertar/actualizar/borrar) que el
> runtime valida y persiste en una transacción. La unicidad de `code` (índice
> `ix_dash_hub_code`) y la inyección de `hub_id`/auditoría las garantiza el runtime.

## 1. `duplicate_dashboard`  (command `dashboards.dashboards.duplicate`)
Origen: `DashboardService.duplicate_dashboard`.
Payload: `{dashboard_id, new_code, new_name}`. Schema: `schemas/dashboard_duplicate.json`.

Lógica no-CRUD (copia en lote, no expresable en una sola sentencia):
- Validar `new_code` y `new_name` no vacíos (lo cubre el schema).
- El runtime precarga: la cabecera del panel origen (`dashboards_dashboard` por `dashboard_id`,
  `hub_id`, no borrado) y sus widgets activos (`dashboards_widget WHERE dashboard_id=:src AND is_deleted=0`).
  Si el panel origen no existe → error `not_found`.
- Comprobar que `new_code` no choca con un panel existente del hub → error `duplicate_code`
  (el runtime puede revalidar contra el índice único).
- Emitir intenciones:
  1. INSERT de la cabecera duplicada: copia `description`, `layout`, `theme`,
     `refresh_interval_sec` y `owner_ref` del origen; fuerza `is_default=0`, `is_public=0`;
     `code=new_code`, `name=new_name`. `new_id` lo genera el runtime.
  2. Por **cada** widget del origen → INSERT de un clon apuntando al `new_id` del panel
     duplicado: copia `widget_type`, `title`, `position_x/y`, `width`, `height`, `config`;
     **resetea** `data_cache=NULL` y `cached_at=NULL` (la caché no se duplica).
- Devolver `{id, code, name, widgets_copied: N}`.
- Emite `dashboards.dashboard.created`.

> Por qué WASM y no SQL: requiere leer N widgets del origen y emitir N+1 inserts con un id de
> cabecera recién generado como FK — fan-out 1→N que no es una sola sentencia declarativa.

## 2. `share_dashboard`  (command `dashboards.shares.share`)
Origen: `DashboardService.share_dashboard`.
Payload: `{dashboard_id, shared_with_ref, access_level}`. Schema: `schemas/share_dashboard.json`.

Lógica no-CRUD (upsert idempotente read-then-branch):
- Validar `shared_with_ref` no vacío y `access_level ∈ {view, edit}` (lo cubre el schema).
- El runtime precarga: el panel (`dashboards_dashboard` por `dashboard_id`, `hub_id`, no borrado)
  → si no existe, error `not_found`. Y la compartición existente que case
  `(dashboard_id, shared_with_ref, is_deleted=0)`.
- Branch idempotente:
  - Si **existe** una compartición previa → UPDATE: `access_level=:access_level`,
    `shared_at = shared_at o :now` (no se machaca si ya había fecha); `created=false`.
  - Si **no existe** → INSERT nueva fila (`shared_at=:now`, `shared_by_ref=:current_user_id`);
    `created=true`. `new_id` lo genera el runtime.
- Devolver `{id, dashboard_id, shared_with_ref, access_level, created}`.
- Emite `dashboards.dashboard.shared`.

> Por qué WASM y no SQL: no hay índice único en `(dashboard_id, shared_with_ref)` (el legacy
> deja duplicados posibles a nivel BD y desempata en código), así que el upsert es un
> read-then-branch (SELECT existente → UPDATE | INSERT) que no es una sola sentencia.

## Notas de paridad con el legacy (sin lógica extra)
- `create_dashboard` / `update_dashboard`: la unicidad de `code` por hub es declarativa
  (índice `ix_dash_hub_code`); el runtime traduce la violación a error `duplicate_code`.
  No requieren WASM.
- `delete_dashboard`: el cascade a widgets + shares (que en SQLAlchemy era `cascade=all,
  delete-orphan`) se reproduce como 3 UPDATEs soft-delete en `commands/dashboard_delete.sql`
  dentro de la misma transacción. No requiere WASM.
- `add_widget` / `update_widget`: la validación de `widget_type` (enum) es declarativa
  (JSON Schema). No requieren WASM.
- `refresh_widget_data`: simple UPDATE de `data_cache`/`cached_at`. No requiere WASM.
- `revoke_share`: simple soft-delete. No requiere WASM.
