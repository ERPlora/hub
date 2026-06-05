-- Marca un hito como 'invoiced' (listo para facturar) y sella invoiced_at. Runtime inyecta :now.
-- Portado de ProjectBillingService.mark_milestone_completed. WHERE status='pending' refuerza la
-- guarda (solo hitos pendientes); 0 filas = estado inválido.
UPDATE project_billing_milestone
SET status = 'invoiced',
    invoiced_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :milestone_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'pending';
