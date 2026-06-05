-- Cancelar una reserva (pending o confirmed). Portado de OnlineBooking.cancel + update_status.
-- La validación de transición ('pending'|'confirmed' -> 'cancelled') es invariant de runtime
-- — ver WASM-TODO.md. El WHERE status IN (...) aplica el guard mínimo a nivel SQL.
UPDATE online_booking_booking
SET status = 'cancelled',
    cancelled_at = :now,
    cancellation_reason = :reason,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :booking_id AND hub_id = :hub_id AND is_deleted = 0
  AND status IN ('pending', 'confirmed');
