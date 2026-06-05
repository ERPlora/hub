# ai_predictions — lógica para handler Rust→WASM (Tier 2)

Fuente legacy: `old_modules/m_ai_predictions/{models.py,services.py}`. El CRUD plano
(alta y desactivación de modelos) ya está en SQL declarativo Tier 0
(`commands/model_create.sql`, `commands/model_deactivate.sql`). Lo que sigue es lógica
de validación numérica, clamping, normalización de decimales y agregación de feedback
que **no** cabe limpiamente en una sola sentencia SQL y debe convertirse en handlers
WASM (`handler/src/lib.rs` → `dist/handler.wasm`).

> Regla hub-next: el WASM **nunca toca la BD**. Recibe el payload + filas leídas por el
> runtime, calcula y devuelve *intenciones* (filas a insertar/actualizar) que el runtime
> valida y persiste en transacción. Los decimales se cuantizan según el modelo legacy.

> El JSON Schema de cada command (referenciado en `module.json`) ya valida tipos básicos,
> enums (`prediction_type`, `feedback_type`) y rango de `confidence ∈ [0,1]`. El WASM se
> ocupa de las reglas que el schema no expresa (clamping, normalización, guardas de estado,
> existencia/actividad del modelo, cómputo de precisión).

---

## 1. `update_model_accuracy`  (command `ai_predictions.models.update_accuracy`)
Origen: `PredictionService.update_model_accuracy`.
- Cargar el modelo por `model_id` (scope `hub_id`); si no existe → error `not_found`.
- **Clamp** de `accuracy_score` al rango `[0, 1]` (valores fuera se recortan, no se rechazan)
  y cuantizar a 4 decimales (`0.0001`).
- `trained_at`: si viene vacío/`null` → usar `now()` del host (capacidad reloj del runtime);
  si viene, parsear ISO-8601 y validar (error `invalid_trained_at` si no parsea).
- Emitir intención de UPDATE sobre `ai_predictions_model`:
  `accuracy_score`, `trained_at`, `updated_by`, `updated_at`.
- Devolver `{id, accuracy_score, trained_at}`. Emite evento `ai_predictions.model.accuracy_updated`.

## 2. `record_prediction`  (command `ai_predictions.predictions.record`)
Origen: `PredictionService.record_prediction`.
- Cargar el modelo por `model_id` (scope `hub_id`); si no existe → error `not_found`.
- **Guarda de estado**: el modelo debe estar `is_active = 1`; si está inactivo →
  error `model_inactive`. (No se permiten predicciones contra un modelo desactivado.)
- Parsear/normalizar decimales:
  - `prediction_value` → cuantizar a 6 decimales (`0.000001`).
  - `confidence` → validar `∈ [0,1]` (el schema ya lo cubre) y cuantizar a 4 decimales (`0.0001`).
- `features_used` debe ser objeto JSON (el schema lo cubre); por defecto `{}`.
- `predicted_at` = `now()` del host.
- Emitir intención de INSERT en `ai_predictions_prediction` con `new_id`, `hub_id`,
  `model_id`, `entity_ref`, valores cuantizados, `predicted_at`, `features_used` (JSON),
  `explanation`, auditoría (`created_by`/`updated_by`/`created_at`/`updated_at`).
- Devolver `{id, model_id, entity_ref, prediction_value, confidence, predicted_at}`.
  Emite evento `ai_predictions.prediction.recorded`.

## 3. `record_feedback`  (command `ai_predictions.feedback.record`)
Origen: `PredictionService.record_feedback`.
- Cargar la predicción por `prediction_id` (scope `hub_id`); si no existe → error `not_found`.
- `feedback_type ∈ {correct, incorrect, partial}` (el schema lo cubre).
- `actual_value`: si vacío/`null` → NULL; si viene, parsear y cuantizar a 6 decimales (`0.000001`)
  (error `invalid_actual` si no parsea).
- `recorded_at` = `now()` del host.
- Emitir intención de INSERT en `ai_predictions_feedback` con `new_id`, `hub_id`,
  `prediction_id`, `actual_value`, `feedback_type`, `notes`, `recorded_at`, auditoría.
- Devolver `{id, prediction_id, feedback_type, actual_value, recorded_at}`.
  Emite evento `ai_predictions.feedback.recorded`.

## 4. `get_model_accuracy`  (command read-only `ai_predictions.models.accuracy`)
Origen: `PredictionService.get_model_accuracy`. Cómputo de agregación, NO muta nada.
- Cargar el modelo por `model_id` (scope `hub_id`); si no existe → error `not_found`.
- `period_days` = `max(1, period_days)` (default 30).
- El runtime lee:
  - todas las `ai_predictions_prediction` del modelo (`model_id`, `hub_id`, no borradas) → para
    contar `predictions_count` y obtener el conjunto de `prediction_id`.
  - todas las `ai_predictions_feedback` del hub cuyo `prediction_id` esté en ese conjunto.
- **Score de precisión** (`correct_count / total_feedback`), con feedback ponderado:
  - `correct` → `1.0`
  - `partial` → `0.5`
  - `incorrect` → `0.0`
  - `score = Σ(peso) / nº_feedback`, cuantizado a 4 decimales (`0.0001`). Sin feedback → `null`.
- Dos ventanas:
  - **overall**: todo el feedback.
  - **recent**: solo feedback con `recorded_at >= now() - period_days`. Comparar fechas de
    forma robusta entre backends (SQLite puede devolver naive; normalizar ambos lados a UTC).
- Devolver `{model_id, code, prediction_type, predictions_count, overall_accuracy,
  overall_feedback_count, recent_accuracy, recent_feedback_count, period_days}`.

---

## Notas de portabilidad
- `features` (lista) y `features_used` (objeto) se almacenan como TEXT JSON en SQLite. El
  WASM/SDK serializa a string JSON antes del INSERT (el bind `:features` de `model_create.sql`
  ya espera un string JSON).
- Todos los decimales se modelan como NUMERIC en SQLite; el WASM debe cuantizar antes de
  devolver la intención para reproducir exactamente el comportamiento legacy
  (`quantize(0.000001)` para valores, `quantize(0.0001)` para confianza/precisión).
- `get_model_accuracy` es read-only: se modela como command con handler WASM (no query) porque
  agrega sobre dos tablas con ponderación y ventana temporal — fuera del alcance de un único
  SELECT declarativo Tier 0.
