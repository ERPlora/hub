-- Marca un evento de webhook como procesado. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de StripeService.mark_webhook_processed (rama sin error_message → status='processed').
-- La rama de fallo (error_message no vacío → status='failed' + error_message) va a runtime
-- por ser condicional sobre el payload — ver WASM-TODO.
UPDATE stripe_webhook_event
SET status = 'processed',
    processed_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE event_id = :event_id AND hub_id = :hub_id AND is_deleted = 0;
