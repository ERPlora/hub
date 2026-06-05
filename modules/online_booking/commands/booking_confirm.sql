-- Confirmar una reserva pendiente. Portado de OnlineBooking.confirm + update_status.
-- IMPORTANTE: la validación de transición de estado (solo 'pending' -> 'confirmed')
-- es un invariant de runtime — ver WASM-TODO.md. El WHERE status='pending' aplica el
-- guard mínimo a nivel SQL (no actualiza si no procede).
UPDATE online_booking_booking
SET status = 'confirmed',
    confirmed_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :booking_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'pending';
