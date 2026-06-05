-- Alta de la cabecera de una proyección. Comando interno invocado por el handler
-- WASM (run_projection) tras construir buckets y calcular puntos. Runtime inyecta
-- :hub_id, :current_user_id, :now; el WASM provee :new_id, :projection_number,
-- :period_start/:period_end, :period_unit, :generated_at, :status, :notes.
INSERT INTO cashflow_forecasting_projection
  (id, hub_id, scenario_id, projection_number, period_start, period_end, period_unit,
   generated_at, generated_by_ref, status, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :scenario_id, :projection_number, :period_start, :period_end, :period_unit,
   :generated_at, :generated_by_ref, :status, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
