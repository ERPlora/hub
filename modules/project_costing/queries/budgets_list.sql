-- Presupuestos de proyecto del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ProjectCostingService.list_budgets. Los binds :project_ref y :status
-- deben pasarse: '' = sin filtro. Orden por created_at desc (más recientes primero).
SELECT id, project_ref, budget_amount, currency, fiscal_year, status,
       approved_by_ref, approved_at, notes, created_at
FROM project_costing_budget
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:project_ref = '' OR project_ref = :project_ref)
  AND (:status      = '' OR status      = :status)
ORDER BY created_at DESC;
