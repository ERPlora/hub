-- Marcar una reserva como completada. Portado de OnlineBooking.complete + update_status.
-- Transición válida: 'confirmed' -> 'completed' (invariant de runtime — ver WASM-TODO.md).
UPDATE online_booking_booking
SET status = 'completed',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :booking_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'confirmed';
