-- Desactivación lógica de una conexión Stripe (NO borra: la saca de futuras selecciones).
-- Portado de StripeService.deactivate_connection. El guard "ya inactiva" va a runtime.
UPDATE stripe_connection
SET is_active = 0,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :id AND hub_id = :hub_id AND is_deleted = 0;
