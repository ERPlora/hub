# project_costing — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_project_costing/{models.py,services.py}`. El CRUD plano y
las transiciones de estado simples (presupuestos draft→active→closed, entradas
pending→approved/rejected) ya están en SQL declarativo Tier 0 (`commands/*.sql`).
Lo que sigue es lógica de **agregación / cálculo de varianza** que produce un
resultado derivado (no una fila) y por tanto no encaja en el patrón
`query` (devuelve filas) ni en un `command` CRUD; va a un handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. El runtime ejecuta las lecturas
> declaradas (queries internas), pasa las filas al WASM, el WASM calcula y
> devuelve el *resultado* (objeto de informe). Todos los importes se manejan con
> precisión decimal `quantize(0.01)` (no float binario).

## 1. `get_project_total_cost`  (command `project_costing.reports.project_total`)
Origen: `ProjectCostingService.get_project_total_cost`.

Payload de entrada:
- `project_ref` (string, requerido) — proyecto a agregar.
- `by_type` (bool, default false) — si true, desglosar por `cost_type`.

Datos que el runtime debe leer y pasar al WASM (lectura interna, NO query pública):
- Todas las `project_costing_entry` del hub con `project_ref = payload.project_ref`,
  `status = 'approved'`, `is_deleted = 0`. Campos: `cost_type`, `amount`.

Lógica (no-CRUD):
- `total = Σ amount` sobre las entradas aprobadas, `quantize(0.01)`.
- `entry_count = nº de entradas`.
- Si `by_type`: agrupar por `cost_type` y sumar → `by_type = { <cost_type>: <total>, ... }`,
  cada total `quantize(0.01)`.

Resultado devuelto:
```json
{ "project_ref": "...", "total": "0.00", "entry_count": 0, "by_type": { "labor": "0.00" } }
```
(`by_type` solo presente si el payload lo pidió.)

## 2. `get_budget_vs_actual`  (command `project_costing.reports.budget_vs_actual`)
Origen: `ProjectCostingService.get_budget_vs_actual`.

Payload de entrada:
- `project_ref` (string, requerido).

Datos que el runtime debe leer y pasar al WASM (lectura interna):
- El presupuesto **activo** más reciente del proyecto: `project_costing_budget` con
  `project_ref = payload.project_ref`, `status = 'active'`, `is_deleted = 0`,
  ordenado por `created_at DESC`, tomando el primero. Campos: `id`, `budget_amount`, `currency`.
  (Puede no existir → presupuesto 0, currency 'EUR'.)
- La suma de `amount` de las `project_costing_entry` del proyecto con
  `status = 'approved'`, `is_deleted = 0` (la legacy lo hace con `SUM` agregado en SQL;
  en hub-next el runtime puede pasar las filas o el sumatorio precomputado).

Lógica (no-CRUD — cálculo de varianza):
- `budget_amount` = importe del presupuesto activo (o 0 si no hay).
- `actual` = Σ amount de entradas aprobadas, `quantize(0.01)`.
- `variance = quantize(budget_amount - actual, 0.01)`.
- `variance_pct`: si `budget_amount != 0` → `quantize(variance / budget_amount * 100, 0.01)`,
  en caso contrario `0.00`.

Resultado devuelto:
```json
{
  "project_ref": "...",
  "budget_id": "uuid|null",
  "budget": "0.00",
  "actual": "0.00",
  "variance": "0.00",
  "variance_pct": "0.00",
  "currency": "EUR"
}
```

## 3. Notas sobre lo NO migrado a WASM (resuelto en Tier 0)
- **Guards de estado** (solo `draft` aprobable, solo `active` cerrable, solo `pending`
  aprobable/rechazable): se materializan en la cláusula `WHERE ... AND status = '<esperado>'`
  de los `commands/*_approve.sql` / `*_close.sql` / `*_reject.sql`. Si 0 filas afectadas,
  el runtime debe traducirlo al error `invalid_state` (equivalente al `self.error(...)` legacy).
- **Append del rastro de rechazo** (`[REJECTED] <reason>` en `notes`): el legacy lo hace en
  Python; aquí se hace con concatenación SQL portable en `entry_reject.sql` (sin timestamp).
  Si se quisiera prefijar timestamp, mover el append a un handler WASM con capacidad de reloj
  del host (no bloqueante).
- **Unicidad de `code` por hub** en categorías: la garantiza el índice
  `uq_pc_category_hub_code`; el error de duplicado lo emite el runtime al violar el índice.
- **Validación de `parent_id`** (existe y pertenece al hub): responsabilidad del runtime
  (FK `ON DELETE SET NULL` + validación de tenancy por `hub_id`).
