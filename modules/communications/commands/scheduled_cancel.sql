-- Cancela un mensaje programado pendiente. Portado de ScheduledService.cancel_scheduled.
-- El guard de "no cancelar si va a enviarse en <1 min" se aplica en el runtime/handler
-- (necesita aritmética de fechas). Aquí solo se cancela si sigue 'pending'.
-- Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE communications_scheduled_message
SET status     = 'cancelled',
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND id = :id AND is_deleted = 0 AND status = 'pending';
