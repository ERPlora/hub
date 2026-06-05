-- Marca el asistente como fallido y registra el mensaje de error (truncado a 500 por el SDK/UI).
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de setup.services.apply_template (rama except).
UPDATE setup_state
SET status        = 'error',
    error_message = :error_message,
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE hub_id = :hub_id AND is_deleted = 0;
