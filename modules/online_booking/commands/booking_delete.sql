-- Borrado lógico (soft-delete) de una reserva. Portado de BookingService.delete_booking.
-- Contrato §2.5: is_deleted=1 + deleted_at=:now (no se borra físicamente).
UPDATE online_booking_booking
SET is_deleted = 1,
    deleted_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :booking_id AND hub_id = :hub_id AND is_deleted = 0;
