-- Centros de coste (dimensión analítica). Runtime inyecta :hub_id.
-- Portado de GeneralLedgerService.list_cost_centers. :active_only = 0 → incluye inactivos.
SELECT id, code, name, parent_id, is_active
FROM general_ledger_cost_center
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = 0 OR is_active = 1)
ORDER BY code ASC;
