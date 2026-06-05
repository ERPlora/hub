# kpis — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_kpis/{models.py,services.py}`. El CRUD plano (alta/edición/
desactivación de KPIs, reconocimiento de alertas) y los listados ya están en SQL declarativo
Tier 0 (`commands/*.sql`, `queries/*.sql`). Lo que sigue es lógica de **clasificación por
umbral**, **inserción condicional de alertas** y **agregación/estadística** que NO cabe en una
sola sentencia SQL y debe convertirse en handler WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas leídas por el runtime,
> calcula y devuelve *intenciones* (filas a insertar/actualizar, comandos a ejecutar, eventos a
> emitir) que el runtime valida y persiste en una transacción. Todos los importes son decimales
> con `quantize(0.0001)` (los modelos usan `Numeric(20,4)`).

---

## 1. `record_value`  (command `kpis.values.record`)  — ÚNICO command WASM declarado
Origen: `KPIService.record_value` + helper `_classify_value`.

Permiso: `kpis.record_kpi`. Transaccional. Emite `kpis.value.recorded` siempre y
`kpis.alert.raised` solo si se genera alerta.

### Entrada (payload, ya validado por `schemas/value_record.json`)
`{kpi_id, period_start, period_end, value, notes?, recorded_by_ref?}`.

### Datos que el runtime debe leer y pasar al handler
La definición del KPI (de `kpis_kpi`, filtrada por hub):
`{id, target_value, target_direction, critical_threshold, warning_threshold, code}`.
Si el KPI no existe / está soft-deleted → error `kpi_not_found` (el handler no inserta nada).

### Lógica no-CRUD
1. **Validación de periodo**: `period_end >= period_start`; ambos requeridos
   (ISO `YYYY-MM-DD`). Si `period_end < period_start` → error `invalid_period`.
2. **Snapshot del objetivo**: `target_at_time = kpi.target_value` (congela el objetivo en el
   momento del registro para histórico fiel, aunque luego cambie la definición).
3. **`computed_at = now`** (capacidad de reloj del host).
4. **Clasificación por umbral** (`_classify_value`), según `target_direction`:
   - `lower_is_better`:
     - `critical_threshold` no nulo y `value >= critical_threshold` → `critical`
     - si no, `warning_threshold` no nulo y `value >= warning_threshold` → `warning`
     - si no → `null` (ok)
   - `higher_is_better` (por defecto):
     - `critical_threshold` no nulo y `value <= critical_threshold` → `critical`
     - si no, `warning_threshold` no nulo y `value <= warning_threshold` → `warning`
     - si no → `null` (ok)
   - Umbrales no definidos (NULL) se saltan.

### Intenciones devueltas
- Insertar 1 fila en `kpis_value`:
  `{id:new_id, hub_id, kpi_id, period_start, period_end, value, target_at_time, computed_at:now,
    recorded_by_ref, notes}` + contrato §2.5 (is_deleted=0, created_by/at, updated_by/at).
- Si la clasificación devuelve `warning`/`critical`, insertar 1 fila en `kpis_alert`:
  `{id:new_id2, hub_id, kpi_id, value_id:<id de la value recién insertada>, alert_type,
    triggered_at:now, message, acknowledged_at:NULL}` + contrato §2.5.
  - `message` = `"KPI {code} {alert_type} | value={value}"` y, si `target_value` no es NULL,
    se añade `" | target={target_value}"` (join con `" | "`, igual que el legacy).
  - Emitir `kpis.alert.raised` con `{alert_id, kpi_id, alert_type}`.
- Emitir siempre `kpis.value.recorded` con `{value_id, kpi_id, value, alert_type}`.

### Salida del command
`{id: value_id, kpi_id, value, alert_type, alert_id}` (alert_type/alert_id = null si no hubo alerta).

---

## 2. `get_kpi_summary`  (resumen estadístico — NO expuesto aún como query)
Origen: `KPIService.get_kpi_summary`. Lectura + cálculo sobre las últimas N filas.

> No está declarado en `module.json` porque las queries declarativas Tier 0 solo hacen SELECT.
> Cuando se necesite exponerlo, será una **query con handler WASM** (o el cálculo lo hará la UI
> sobre `kpis.values.list`). Documentado aquí para no perder la lógica.

### Datos
Las últimas `periods` (def. 12) filas de `kpis_value` para el KPI (orden `period_start DESC`)
+ la definición del KPI (`target_value`, `target_direction`).

### Lógica
- `periods <= 0` → error `invalid_period`.
- Sin valores → `{trend:'flat', avg:null, latest:null, vs_target:null, samples:0}`.
- Reordenar cronológicamente (las filas vienen newest-first → invertir).
- `avg = quantize(Σ value / n, 0.0001)`.
- `latest` = valor más reciente.
- `trend`: comparar `latest` vs penúltimo → `up` / `down` / `flat` (con n<2 → `flat`).
- `vs_target` (solo si `target_value` no es NULL):
  - `higher_is_better`: latest > target → `above`; == → `on_track`; < → `below`.
  - `lower_is_better`: latest < target → `above` (mejor); == → `on_track`; > → `below`.
- Salida: `{kpi_id, trend, avg, latest, vs_target, samples}`.

---

## 3. `get_dashboard_summary`  (agregado del panel — NO expuesto aún como query)
Origen: `KPIService.get_dashboard_summary`. Agrega el estado de TODOS los KPIs activos.

> Igual que la pieza 2: agregación multi-fila con sub-consultas por KPI → handler WASM (o vista
> agregada). No es una sola SELECT trivial. Documentado para preservar la lógica.

### Datos
- Todos los `kpis_kpi` activos del hub (filtro opcional `category`).
- Por cada KPI con `target_value` no nulo: su `kpis_value` más reciente (`period_start DESC`).
- Conteo de `kpis_alert` no reconocidas por tipo (`warning`, `critical`).

### Lógica (buckets vs objetivo)
Para cada KPI activo:
- `target_value` NULL → bucket `no_target`.
- sin valores registrados → bucket `no_data`.
- con valor: comparar latest vs target según `target_direction` (misma regla que pieza 2):
  `above` / `on_track` / `below`.

### Salida
```
{
  kpi_total: <nº de KPIs activos>,
  buckets: { above, on_track, below, no_data, no_target },
  alerts:  { warning, critical, unacknowledged_total }
}
```

---

## 4. Audit-trail textual en alertas (Tier 1, no crítico)
Origen: `KPIService.acknowledge_alert(notes=...)`.
- Hoy `commands/alert_acknowledge.sql` estampa `acknowledged_at/by` pero **no** hace el append
  `"{message}\n[ACK] {notes}"` al campo `message` cuando llegan notas.
- Si se quiere conservar ese rastro textual, moverlo a un handler WASM que componga el nuevo
  `message` (append con timestamp/notas) — capacidad de "reloj" del host. No bloqueante.
