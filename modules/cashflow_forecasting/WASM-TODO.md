# cashflow_forecasting — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_cashflow_forecasting/{models.py,services.py}`. El CRUD plano
de escenarios (create / update / deactivate) ya está en SQL declarativo Tier 0
(`commands/scenario_*.sql`). Lo que sigue es lógica de cálculo / batch / agregación cross-fila
que **no** cabe en una sola sentencia SQL y debe convertirse en handler WASM
(`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + datos leídos por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en una transacción. Todos los importes con `quantize(0.0001)` (Numeric(18,4)
> en el legacy). Las fechas son ISO `YYYY-MM-DD`.

Tres funciones exportadas: `run_projection`, `compare_scenarios`, `get_break_even_point`.
Las dos últimas son de **solo-lectura** (no persisten) pero se exponen como commands handler
porque agregan sobre N filas; el runtime las invoca y devuelve el resultado al SDK.

---

## 1. `run_projection`  (command `cashflow_forecasting.projections.run`)
Origen: `CashflowService.run_projection` + helpers `_period_length`, `_bucket_movements`,
`_generate_projection_number`, `_source_for`.

Payload (ver `schemas/run_projection.json`):
`{scenario_id, period_start, period_end, period_unit, inflows[], outflows[]}` donde cada
movimiento es `{date?: YYYY-MM-DD|null, amount: number, source?: recurring|expected|historical}`.

Datos que el runtime debe leer y pasar al WASM:
- El escenario (`cashflow_forecasting.scenarios.get` con `scenario_id`) → necesita
  `opening_balance` como saldo inicial. Si no existe → error `scenario_not_found`.

Lógica:
1. Validar `period_end >= period_start` (si no → error `invalid_period`).
2. **Construir buckets de periodos** (`_period_length`): partiendo de `period_start`, avanzar
   en saltos de `period_unit` (day=1d, week=7d, month≈30d) hasta `period_end`. Cada bucket es
   `[ps, pe]` con `pe = min(ps + len - 1d, period_end)`; el cursor salta a `pe + 1d`.
3. **Distribuir movimientos en buckets** (`_bucket_movements`), por separado inflows y outflows:
   - Movimiento **con fecha**: suma su `amount` al bucket cuyo `[ps, pe]` contiene la fecha.
   - Movimiento **sin fecha** (o fecha inválida): se acumula y al final se reparte **a partes
     iguales** entre todos los buckets (`share = quantize(undated_total / n, 0.0001)`), con el
     **remanente** sumado al último bucket.
   - `amount` no parseable → se ignora ese movimiento.
4. **Etiqueta `source` del punto** (`_source_for` + regla de combinación): si todos los inflows
   comparten un único `source` válido, ese; si no, `expected`. Igual para outflows. La etiqueta
   final del punto es la del inflow si coincide con la del outflow, si no `expected`.
5. **Número de proyección** (`_generate_projection_number`): `CFP-YYYYMMDD-NNNN` con `NNNN`
   aleatorio de 4 dígitos. En hub-next preferir un **counter atómico del runtime** por hub+día
   (UPSERT) en lugar de aleatorio, para evitar colisiones; el WASM solo formatea con el nº dado.
   (`generated_at` = "ahora" lo aporta el reloj del host.)
6. **Calcular puntos** (bucle de `run_projection`): `running_balance = opening_balance`. Por bucket:
   - `inflow = quantize(bucket_in, 0.0001)`, `outflow = quantize(bucket_out, 0.0001)`.
   - `net = quantize(inflow - outflow, 0.0001)`.
   - `opening = quantize(running_balance, 0.0001)`, `closing = quantize(opening + net, 0.0001)`.
   - `running_balance = closing`.
7. Si el bucketing lanzase excepción → `status = 'failed'`, `notes = motivo`, buckets a 0
   (el legacy degrada en vez de abortar). En el camino normal `status = 'completed'`.

Intenciones a devolver al runtime (todo en una transacción):
- 1 fila en `cashflow_forecasting_projection` (cabecera: scenario_id, projection_number,
  period_start/end, period_unit, generated_at, status, notes).
- N filas en `cashflow_forecasting_point` (una por bucket, con los importes calculados y `source`).
- Emite `cashflow_forecasting.projection.completed` (ya declarado en module.json).
- Retorno al SDK: `{id, projection_number, status, points_count, scenario_id, final_balance}`.

> Usa los commands internos `cashflow_forecasting._insert_projection` /
> `cashflow_forecasting._insert_point` (ya declarados en module.json + `commands/_insert_*.sql`),
> análogos al patrón `_insert_line` documentado en `quotes/WASM-TODO.md`: el WASM devuelve las
> intenciones y el runtime las persiste vía estos commands dentro de la misma transacción.

---

## 2. `compare_scenarios`  (command `cashflow_forecasting.scenarios.compare`, solo-lectura)
Origen: `CashflowService.compare_scenarios`.

Payload: `{scenario_id_a, scenario_id_b}` (deben diferir → si no, error `same_scenario`).

Datos que el runtime debe leer y pasar al WASM:
- Ambos escenarios (validar existencia → `scenario_a_not_found` / `scenario_b_not_found`).
- La **última proyección `completed`** de cada uno (ORDER BY created_at DESC LIMIT 1). Si a
  cualquiera le falta → error `missing_projection`.
- Todos los `cashflow_forecasting_point` de ambas proyecciones (ordenados por `period_start`).

Lógica:
- Indexar puntos por `period_start` (clave ISO) en cada escenario; recorrer la **unión ordenada**
  de claves.
- Por periodo: `closing_balance_a/b` (o null si falta en un lado); si ambos presentes,
  `diff_closing = quantize(closing_b - closing_a, 0.0001)`, e igual `diff_inflows`, `diff_outflows`.
- Agregados por escenario: `total_inflows`, `total_outflows` (suma de puntos), `final_balance`
  (closing del último punto).
- Retorno: `{scenario_a:{...}, scenario_b:{...}, diff_final_balance, matched_periods,
  total_periods, periods:[fila por periodo]}`. No persiste nada.

---

## 3. `get_break_even_point`  (command `cashflow_forecasting.scenarios.break_even`, solo-lectura)
Origen: `CashflowService.get_break_even_point`.

Payload: `{scenario_id}`.

Datos que el runtime debe leer y pasar al WASM:
- El escenario (validar → `scenario_not_found`).
- Su **última proyección `completed`** (si no hay → error `missing_projection`).
- Los `cashflow_forecasting_point` de esa proyección ordenados por `period_start`.

Lógica (break-even **sostenido**):
- El break-even es el **primer** periodo cuyo `closing_balance > 0` **y** todos los periodos
  posteriores también tienen `closing_balance > 0`. Barrido O(n²) sobre los puntos (n pequeño).
- Retorno: `{scenario_id, scenario_code, projection_id, total_periods, break_even: punto|null}`.
  No persiste nada.

---

## Notas de portabilidad
- `Numeric(18,4)` legacy → en SQLite las columnas son `NUMERIC`; el WASM trabaja con decimales
  fijos y `quantize(0.0001)` para igualar el comportamiento de `Decimal`.
- `parameters` del escenario es JSON guardado como TEXT; hoy no se usa en el cálculo (reservado
  para reglas futuras de proyección). Si se introduce lógica basada en `parameters`, documentarla aquí.
