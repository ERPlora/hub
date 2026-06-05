-- Baja (soft-delete) de una suscripción. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de ReportService.unsubscribe.
UPDATE reports_subscription
SET is_deleted = 1,
    deleted_at = :now,
    is_active  = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :subscription_id AND hub_id = :hub_id AND is_deleted = 0;
