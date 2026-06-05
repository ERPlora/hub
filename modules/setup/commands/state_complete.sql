-- Marca el asistente como completado (la orquestación WASM ya sembró todo con éxito).
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de setup.services.apply_template (éxito).
-- Solo actualiza la fila existente del singleton; el alta inicial la hace state_start.
UPDATE setup_state
SET status        = 'completed',
    error_message = '',
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE hub_id = :hub_id AND is_deleted = 0;
