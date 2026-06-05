-- Marca un evento de webhook como procesado (idempotente del lado de la aplicación).
-- Runtime inyecta :hub_id, :current_user_id, :now. Portado de UberEatsService.mark_event_processed.
-- El bind es :event_id (id de Uber), no el PK interno, igual que en el legacy.
UPDATE uber_eats_event
SET status      = 'processed',
    processed_at = :now,
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE event_id = :event_id AND hub_id = :hub_id AND is_deleted = 0;
