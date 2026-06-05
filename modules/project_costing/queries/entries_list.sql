-- Entradas de coste del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ProjectCostingService.list_cost_entries (por defecto status='approved').
-- Los binds :project_ref/:cost_type/:status deben pasarse: '' = sin filtro.
-- :limit acota el resultado. Orden por entry_date desc.
SELECT id, project_ref, entry_date, cost_type, description, amount, hours,
       employee_ref, supplier_ref, status, notes, created_at
FROM project_costing_entry
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:project_ref = '' OR project_ref = :project_ref)
  AND (:cost_type   = '' OR cost_type   = :cost_type)
  AND (:status      = '' OR status      = :status)
ORDER BY entry_date DESC
LIMIT :limit;
