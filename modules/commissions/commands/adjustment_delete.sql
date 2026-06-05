-- Borrado lógico (soft-delete) de ajuste manual. Runtime inyecta :hub_id, :now,
-- :current_user_id. Portado de routes.adjustment_delete.
UPDATE commissions_adjustment
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :adjustment_id;
