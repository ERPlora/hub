-- Una proyección por id (scope hub_id). Portado de CashflowService.get_projection.
-- Los puntos por periodo se piden aparte con cashflow_forecasting.points.list.
SELECT id, scenario_id, projection_number, period_start, period_end, period_unit,
       generated_at, generated_by_ref, status, notes, created_at
FROM cashflow_forecasting_projection
WHERE id = :projection_id AND hub_id = :hub_id AND is_deleted = 0;
