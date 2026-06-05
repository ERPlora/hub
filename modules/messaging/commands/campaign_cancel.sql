-- Cancela una campaña (transición simple). Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de Campaign.cancel. Solo desde estados no terminales.
UPDATE messaging_campaign
SET status     = 'cancelled',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0
  AND status IN ('draft', 'scheduled', 'sending');
