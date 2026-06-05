-- Primitiva interna: aplica una transición de estado a una solicitud (la decide el handler
-- WASM tras comprobar saldo/permisos). Usada por approve_request. Runtime inyecta binds.
UPDATE leave_request
SET status      = :status,
    approved_by = :approved_by,
    approved_at = :approved_at,
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE id = :request_id AND hub_id = :hub_id AND is_deleted = 0;
