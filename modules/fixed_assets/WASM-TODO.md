# fixed_assets — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_fixed_assets/{models.py,services.py}`. El CRUD plano
(alta/edición de activos, listados) ya está en SQL declarativo Tier 0
(`commands/asset_register.sql`, `commands/asset_update.sql`, `queries/*.sql`). Lo que
sigue es **lógica contable de amortización, autonumeración, baja con cálculo de
gain/loss y el batch mensual** que no cabe en una sola sentencia SQL y debe convertirse
en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el
> runtime le entrega (el activo, sus entradas posteadas), calcula y devuelve *intenciones*
> (filas a insertar/actualizar, comandos de persistencia) que el runtime valida y ejecuta en
> una transacción. Todos los importes se cuantizan a 2 decimales con `ROUND_HALF_UP`
> (`quantize(0.01)`), igual que el legacy (`_money`).

## Constantes / enums
- `ASSET_STATUSES = active | disposed | written_off | in_maintenance`
- `DEPRECIATION_METHODS = linear | declining | units_of_production`
- `DISPOSAL_TYPES = sale | scrap | donation | loss`

---

## 0. Helpers de cálculo (compartidos por todas las piezas)
Origen: `services.py` (`_money`, `_days_between`, `_annual_linear_amount`,
`_calculate_period_amount`, `_month_range`).

### 0.1 `_money(x)` — redondeo
`quantize(x, 0.01, ROUND_HALF_UP)`. Aplicar a todo importe devuelto.

### 0.2 `_days_between(start, end)`
Días **inclusivos**: `(end - start).days + 1`, con piso 0.

### 0.3 `_annual_linear_amount(asset)`
- `life = useful_life_years`; si `life <= 0` → `0.00`.
- `depreciable = acquisition_cost - residual_value`; si `<= 0` → `0.00`.
- Devuelve `depreciable / life` (sin redondear aún).

### 0.4 `_calculate_period_amount(asset, period_start, period_end)` — **núcleo**
1. `days = _days_between(start, end)`; si `<= 0` → `0.00`.
2. `depreciable_base = acquisition_cost - residual_value`; si `<= 0` → `0.00`.
3. `remaining = depreciable_base - accumulated_depreciation`; si `<= 0` → `0.00`.
4. Por método:
   - **declining**: `rate = 2 / life` (si `life <= 0` → `0.00`);
     `book_value = acquisition_cost - accumulated_depreciation`;
     `annual = book_value * rate`; `amount = annual * days / 365`.
   - **linear** y **units_of_production** (fallback; el legacy no tiene feed de uso):
     `annual = _annual_linear_amount(asset)`; `amount = annual * days / 365`.
5. Clamp: si `amount < 0` → 0; si `amount > remaining` → `remaining`.
6. Devolver `_money(amount)`.

> NOTA contable a decidir en producto: `units_of_production` hoy degrada a lineal. Si se
> quiere implementar de verdad hace falta un payload de uso (`units_used` / `total_units`).

### 0.5 `_month_range(month)` — "YYYY-MM" → (primer_día, último_día)
Parsear `month-01`; si mes==12 el siguiente primero es del año+1; `end = next_first - 1 día`.
Mes inválido → error `invalid_month`.

---

## 1. `dispose_asset`  (command `fixed_assets.assets.dispose`)
Origen: `FixedAssetService.dispose_asset`.
- Cargar el activo (runtime lo entrega por `asset_id`, scope `hub_id`). No existe → `not_found`.
- Validar `disposal_type ∈ DISPOSAL_TYPES` (lo cubre el schema, revalidar defensivo).
- **Guarda de estado**: si `status ∈ {disposed, written_off}` → error `invalid_state`
  ("Asset is already …").
- Parsear `sale_price` (`_money`) y `disposal_date` (ISO o **hoy** si vacío — capacidad reloj del host).
- `book_value = current_book_value`; `gain_loss = _money(sale_price - book_value)`.
- `final_status = written_off` si `disposal_type ∈ {scrap, loss}`, si no `disposed`.
- Intenciones:
  - INSERT en `fixed_assets_disposal` (id nuevo, hub_id, asset_id, disposal_date, disposal_type,
    sale_price, gain_loss, notes).
  - UPDATE `fixed_assets_asset.status = final_status` (+ updated_by/updated_at).
- Emitir `fixed_assets.asset.disposed` con `{asset_id, disposal_type, gain_loss, asset_status}`.
- Devolver `{id, asset_id, disposal_type, disposal_date, sale_price, gain_loss, asset_status}`.

---

## 2. `post_depreciation`  (command `fixed_assets.depreciations.post`)
Origen: `FixedAssetService.post_depreciation`.
- Cargar activo. No existe → `not_found`.
- **Guarda de estado**: si `status ∈ {disposed, written_off}` → error `invalid_state`.
- Parsear `period_start`/`period_end` (requeridos). `end < start` → error `invalid_period`.
- `amount = _calculate_period_amount(asset, start, end)` (pieza 0.4).
- `new_acc = _money(accumulated_depreciation + amount)`.
- `new_book = acquisition_cost - new_acc`; si `< residual_value` → `residual_value`; `_money`.
- Intenciones:
  - INSERT `fixed_assets_depreciation` (period_start/end, depreciation_amount=amount,
    accumulated_after=new_acc, book_value_after=new_book, posted=1, posted_at=now).
  - UPDATE activo: `accumulated_depreciation = new_acc`, `current_book_value = new_book`.
- Emitir `fixed_assets.depreciation.posted` con `{asset_id, depreciation_amount, book_value_after}`.
- Devolver `{id, asset_id, period_start, period_end, depreciation_amount, accumulated_after, book_value_after}`.

---

## 3. `run_monthly_depreciation`  (command `fixed_assets.depreciations.run_monthly`, batch)
Origen: `FixedAssetService.run_monthly_depreciation`. **Batch sobre N filas → WASM.**
- `(start, end) = _month_range(month)` (pieza 0.5). Inválido → `invalid_month`.
- El runtime entrega **todos los activos `status='active'`** del hub.
- Por cada activo: `amount = _calculate_period_amount(...)`.
  - Si `amount <= 0` → registrar en `results` `{asset_id, asset_number, skipped:true,
    reason:"no_depreciable_amount"}` y continuar (no postear).
  - Si `amount > 0`: misma intención que la pieza 2 (INSERT entry + UPDATE totales del activo),
    acumular `total_posted += amount` y `posted_count += 1`.
- Cada activo debe persistirse de forma atómica (el legacy abre un `atomic()` por activo).
- Emitir `fixed_assets.depreciation.posted` (por lote, o uno por entrada — decisión de producto).
- Devolver `{month, period_start, period_end, assets_processed, entries_posted,
  total_depreciation, results:[…]}`.

---

## 4. Autonumeración de activos (`generate_asset_number`)
Origen: `FixedAssetService._generate_asset_number`. Lo necesita `asset_register` (el SQL
declarativo espera `:asset_number` ya provisto).
- Formato `FA-YYYYMMDD-NNNN` (NNNN = secuencia por hub+día, 4 dígitos).
- El legacy cuenta los activos cuyo `asset_number` empieza por el prefijo de hoy y suma 1
  (ventana SELECT→formato). En hub-next debe ser **atómico** (counter UPSERT como capacidad
  del runtime, igual que `quotes`) para evitar colisiones concurrentes; el WASM solo formatea
  `FA-{day}-{n:04d}` con el número devuelto.
- Aquí va también la **validación previa al INSERT** que el SQL no cubre: método válido,
  importes no negativos, `residual_value <= acquisition_cost`, unicidad de `code` por hub
  (el índice `ix_fa_hub_code` la respalda, pero conviene error legible `duplicate_code`).

## 5. Recálculo de `current_book_value` en `asset_update`
Origen: `FixedAssetService.update_asset` (rama final). El SQL declarativo espera
`:current_book_value` ya calculado.
- Si cambian `acquisition_cost` o `residual_value`:
  `book = acquisition_cost - accumulated_depreciation`; si `< residual_value` → `residual_value`;
  `_money`. Si no cambian, mantener el valor actual.
- Validaciones whitelisteadas (método, status, fechas, importes, vida) que el schema cubre
  parcialmente; revalidar defensivo en el handler/runtime.

---

## 6. Queries de reporting NO migradas (candidatas a query/handler futuro)
El legacy expone como `@action` de lectura, pero **no** se han portado a `queries/*.sql` por
requerir agregación/recálculo que excede una SELECT simple:
- `get_asset_value(asset_id, as_of_date)`: re-deriva el valor contable a una fecha sumando las
  entradas posteadas con `period_end <= as_of_date`. Agregación + clamp a residual → handler WASM
  o query con agregación si el dialecto lo permite.
- `get_depreciation_summary(period_start, period_end)`: agrega importes por `asset_category`
  sobre las entradas en rango (join entry↔asset). GROUP BY con join cross-tabla del propio
  módulo → query SQL futura o handler.
- `calculate_depreciation(asset_id, period_start, period_end)`: **preview** (no postea); reutiliza
  pieza 0.4 y devuelve `{depreciation_amount, projected_accumulated, projected_book_value, method}`.
  Candidato a handler WASM de solo-lectura cuando se implemente el preview en UI.

No se añadieron entradas de navegación ni commands para estas hasta que se implementen
(regla: sin nav/contrato muerto).
