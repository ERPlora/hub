-- Lista de runs MRP del hub (más recientes primero), con filtro de status opcional.
-- Runtime inyecta :hub_id. Portado de MRPService.list_runs.
-- (:status = '' → sin filtro de estado.)
SELECT id, run_number, run_date, horizon_days, status,
       started_at, completed_at, total_requirements, total_suggestions, parameters
FROM mrp_run
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
