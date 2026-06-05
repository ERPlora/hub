# forecasting — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_forecasting/{models.py,services.py}`. El CRUD plano de
modelos (`forecasting.models.create|update|deactivate`) ya está en SQL declarativo
Tier 0 (`commands/*.sql`), y las lecturas en `queries/*.sql`. Lo que sigue es lógica
de cálculo de series temporales / batch / agregación que **no** cabe en una sola
sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + las filas que el
> runtime le entregue (modelo, puntos existentes) y devuelve *intenciones* (filas a
> insertar/actualizar) que el runtime valida y persiste en una transacción. Todos los
> importes se redondean con `quantize(0.0001)` (4 decimales, como `Numeric(18,4)` legacy).

## Helpers de cálculo (puros, portados de services.py)

- `_moving_average(values, window)`: media de los últimos `window` elementos (o todos si
  hay menos). `Decimal("0")` si la serie está vacía. Redondeo `0.0001`.
- `_linear_trend(values) -> (intercept, slope)`: ajuste mínimo-cuadrados `y = a + b*x`
  sobre índices `0..n-1`. `n==0 → (0,0)`; `n==1 → (values[0], 0)`. `slope = num/den` con
  `den = Σ(x-mean_x)²` (si `den==0 → slope=0`). Redondeo `0.0001`.
- `_values_from_historical(historical_data)`: extrae la serie numérica de
  `[{value|y|amount: x}, ...]`; valores no parseables → `0`.
- `_period_length(period_unit)`: `day→1d`, `week→7d`, `quarter→90d`, default `month→30d`.
- `_generate_forecast_number()`: `FC-YYYYMMDD-NNNN` con sufijo aleatorio de 4 dígitos.
  En hub-next usar la capacidad de "reloj" del host para `YYYYMMDD` y el sufijo. Si se
  requiere unicidad estricta por hub+día, resolver como counter UPSERT del runtime
  (mismo patrón que `quotes`), no como aleatorio.

## 1. `run_forecast`  (command `forecasting.forecasts.run`)
Origen: `ForecastingService.run_forecast`. Cálculo + batch de puntos. **Núcleo del módulo.**

Entrada (payload validado por `schemas/forecast_run.json`): `model_id`, `horizon_periods`
(default 12, clamp `>=1`), `period_unit` (enum), `historical_data` (lista de dicts).
El runtime entrega además la fila del modelo (`forecasting.models.get`): `model_type`,
`parameters` (JSON), etc.

Pasos:
1. `history = _values_from_historical(historical_data)`; `horizon = max(1, horizon_periods)`.
2. Calcular `predictions: list[Decimal]` según `model_type`:
   - **`moving_average`**: `window = int(params.get("window", 3))`. Iterar `horizon` veces:
     `pred = _moving_average(series, window)`, `predictions.append(pred)`, y **realimentar**
     `series.append(pred)` (predicción recursiva).
   - **`linear_trend`**: `(intercept, slope) = _linear_trend(history)`; para `i` en `0..horizon-1`:
     `x = len(history)+i`; `pred = quantize(intercept + slope*x, 0.0001)`.
   - **`exponential_smoothing` / `seasonal` / `manual`**: placeholder → `horizon` ceros
     (`0.0000`). (Pendiente de implementar de verdad; legacy también es placeholder.)
   - Si el cálculo lanza excepción → `status="failed"`, `predictions=[]`,
     `notes = str(exc)` (`failure_reason`).
3. Construir intenciones:
   - **Cabecera** `forecasting_forecast`: `forecast_number` (helper), `model_id`,
     `forecast_horizon_periods=horizon`, `period_unit`, `generated_at=now`, `status`,
     `notes=failure_reason`, `accuracy_score=NULL`. Estándar de fila: `hub_id`,
     `created_by/updated_by=current_user`, `created_at/updated_at=now`.
   - **Puntos** `forecasting_point` (uno por predicción): `start = today()`;
     `period_start = start + period_len*i`; `period_end = period_start + period_len - 1d`;
     `predicted_value = value`; bandas simples ±10%: `lower = quantize(value*0.90, 0.0001)`,
     `upper = quantize(value*1.10, 0.0001)`; `confidence = 0.9500`.
   - **Update modelo**: `forecasting_model.last_trained_at = generated_at` (el WASM emite
     la intención; el runtime ejecuta el UPDATE — el WASM no escribe BD).
4. Emitir `forecasting.forecast.completed` con `{id, forecast_number, status, points_count,
   model_type}`.

Por qué WASM: bucle de predicción recursiva, ajuste lineal, generación de N filas de puntos
con aritmética decimal y derivación de fechas por periodo → no es una sola sentencia SQL.

## 2. `record_accuracy`  (command `forecasting.forecasts.record_accuracy`)
Origen: `ForecastingService.record_accuracy`. Cálculo de MAPE y persistencia de `accuracy_score`.

Entrada (`schemas/forecast_record_accuracy.json`): `forecast_id`, `actual_values` (dict no
vacío ISO `period_start` → real numérico). El runtime entrega los puntos del forecast
(`forecasting.points.list`).

Pasos:
1. Validar puntos no vacíos (si no → error `no_points`).
2. Para cada punto cuyo `period_start.isoformat()` esté en `actual_values` y con
   `actual != 0`: `err_pct = abs(actual - predicted_value) / abs(actual)`; acumular
   `total_pct_err`, `matched += 1`. Reales no parseables o `==0` se ignoran.
3. Si `matched == 0` → error `no_match`.
4. `mape = total_pct_err / matched`; `score = clamp(1 - mape, 0, 1)`; `quantize(0.0001)`.
5. Intención: `UPDATE forecasting_forecast SET accuracy_score = score` (+ `updated_by/at`)
   para `forecast_id` del hub. El WASM emite la intención; el runtime persiste.
6. Emitir `forecasting.forecast.accuracy_recorded` con `{id, accuracy_score, mape,
   matched_periods}`.

Por qué WASM: agregación condicional sobre N puntos (matching por clave + filtros) y MAPE
con clamp → no cabe en una sola UPDATE declarativa.

## 3. `compare_forecast_to_actual`  (lectura derivada — NO migrada como command)
Origen: `ForecastingService.compare_forecast_to_actual` (read-only `@action`).

Calcula el diff por periodo entre `predicted_value` y `actual_values` aportados por el
caller (no almacenados), más agregados (`total_abs_diff`, `mape`, `matched_periods`).
Como es **solo lectura y depende de un input efímero del cliente**, NO se añadió ni como
query SQL (necesita aritmética por fila + agregados que SQL declarativo no compone bien con
un dict de entrada) ni como command (no muta). Opciones para hub-next:
- (A) **Cliente-side**: el WC obtiene los puntos con `forecasting.points.list` y calcula el
  diff en JS contra los `actual_values` introducidos (sin BD; recomendado, es presentación).
- (B) Si se necesita servidor: exponer una función WASM read-only que reciba puntos +
  `actual_values` y devuelva el desglose. Misma fórmula que pieza 2 más, por periodo:
  `diff = quantize(actual - predicted, 0.0001)`, `pct_error = quantize(abs(diff)/abs(actual), 0.0001)`
  (solo si `actual != 0`), listando también los periodos sin actual (`actual=null, diff=null`).

No se creó entrada de nav/command para esto a propósito (regla: sin paths colgantes).

## 4. Validaciones que el runtime/Schema ya cubren (no van a WASM)
- `model_type`/`target_metric`/`period_unit` ∈ enums → JSON Schema.
- `code` único por hub en alta → índice `ix_forecasting_model_hub_code` (el runtime traduce
  la violación de UNIQUE a error `duplicate_code`).
- "modelo ya inactivo" en `deactivate` y "campos desconocidos" en `update` → el legacy lo
  resolvía en servicio; en hub-next es la query previa del SDK + `additionalProperties:false`
  del schema de update. No requiere WASM.
