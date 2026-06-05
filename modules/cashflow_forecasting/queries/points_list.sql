-- Puntos por periodo de una proyección, ordenados cronológicamente.
-- Runtime inyecta :hub_id. Portado de CashflowService.get_projection (include_points).
SELECT id, projection_id, period_start, period_end, opening_balance,
       total_inflows, total_outflows, closing_balance, net_change, source
FROM cashflow_forecasting_point
WHERE hub_id = :hub_id AND is_deleted = 0
  AND projection_id = :projection_id
ORDER BY period_start ASC;
