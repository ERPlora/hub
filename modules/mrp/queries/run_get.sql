-- Una cabecera de run MRP por id (scope hub_id). Portado de MRPService.get_run.
-- El SDK/UI carga aparte sus requirements/suggestions con las queries dedicadas.
SELECT id, run_number, run_date, horizon_days, status,
       started_at, completed_at, total_requirements, total_suggestions, parameters
FROM mrp_run
WHERE id = :run_id AND hub_id = :hub_id AND is_deleted = 0;
