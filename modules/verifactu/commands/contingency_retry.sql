-- Reencolar manualmente una entrada de la cola de contingencia para reintento.
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de routes.retry_record.
-- Resetea attempts y la pone en 'pending' con next_attempt_at = ahora.
UPDATE verifactu_contingencyqueue
SET status          = 'pending',
    attempts        = 0,
    next_attempt_at = :now,
    updated_by      = :current_user_id,
    updated_at      = :now
WHERE id = :queue_id AND hub_id = :hub_id AND is_deleted = 0;
