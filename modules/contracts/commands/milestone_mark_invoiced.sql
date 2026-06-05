-- Marca un hito como facturado (fija invoiced_at = :now). Runtime inyecta :hub_id,
-- :current_user_id, :now. Portado de ContractService.mark_milestone_invoiced.
-- El guard is_invoiced = 0 en el WHERE evita re-facturar (0 filas = already_invoiced).
UPDATE contracts_milestone
SET is_invoiced = 1,
    invoiced_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :milestone_id AND hub_id = :hub_id AND is_deleted = 0
  AND is_invoiced = 0;
