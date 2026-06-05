-- Alta de un punto de proyección (un periodo). Comando interno invocado por el
-- handler WASM (run_projection) una vez calculados los saldos del periodo.
-- Runtime inyecta :hub_id, :current_user_id, :now; el WASM provee :new_id,
-- :projection_id, :period_start/:period_end y los importes ya con quantize(0.0001).
INSERT INTO cashflow_forecasting_point
  (id, hub_id, projection_id, period_start, period_end, opening_balance,
   total_inflows, total_outflows, closing_balance, net_change, source,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :projection_id, :period_start, :period_end, :opening_balance,
   :total_inflows, :total_outflows, :closing_balance, :net_change, :source,
   0, :current_user_id, :current_user_id, :now, :now);
