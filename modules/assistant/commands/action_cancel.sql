-- Cancela (descarta) un log de acción pendiente del usuario activo. Runtime inyecta
-- :hub_id, :current_user_id, :now. Portado de cancel_action (que hacía session.delete);
-- aquí es soft-delete por el contrato de fila §2.5. Sólo el dueño y sólo si está pendiente.
UPDATE assistant_action_log
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE hub_id = :hub_id AND is_deleted = 0
  AND id = :log_id
  AND created_by = :current_user_id
  AND confirmed = 0;
