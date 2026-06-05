-- Marcar una reserva como no-show. Portado de OnlineBooking.mark_no_show + update_status.
-- Transición válida: 'confirmed' -> 'no_show' (invariant de runtime — ver WASM-TODO.md).
UPDATE online_booking_booking
SET status = 'no_show',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :booking_id AND hub_id = :hub_id AND is_deleted = 0
  AND status = 'confirmed';
