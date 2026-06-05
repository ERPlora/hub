-- Ejecuciones de proyección recientes, con filtro opcional por escenario.
-- Runtime inyecta :hub_id. Portado de CashflowService.list_projections.
-- :scenario_id ('' = sin filtro); :limit acota el nº de filas.
SELECT id, scenario_id, projection_number, period_start, period_end, period_unit,
       generated_at, generated_by_ref, status, notes, created_at
FROM cashflow_forecasting_projection
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:scenario_id = '' OR scenario_id = :scenario_id)
ORDER BY created_at DESC
LIMIT :limit;
