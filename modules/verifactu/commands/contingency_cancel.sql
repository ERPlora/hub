-- Cancelar una entrada de la cola de contingencia (status='cancelled').
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de routes.cancel_queue_entry.
-- NOTA: el rastro de auditoría (insertar VerifactuEvent) lo añade el handler/runtime;
-- aquí solo se marca cancelada (ver WASM-TODO para el evento de auditoría).
UPDATE verifactu_contingencyqueue
SET status     = 'cancelled',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :queue_id AND hub_id = :hub_id AND is_deleted = 0;
