-- Desactivación lógica de una conexión (deja de ser elegible para llamadas a la API).
-- Portado de CourierService.deactivate_connection. NO borra la fila.
UPDATE courier_integrations_connection
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :connection_id AND hub_id = :hub_id AND is_deleted = 0;
