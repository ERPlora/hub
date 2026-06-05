-- Una reserva por id (scope hub_id). Portado de BookingService.get_booking.
SELECT id, booking_reference, customer_id, customer_name, customer_email,
       customer_phone, service_id, service_name, staff_id, staff_name,
       booking_date, booking_time, duration_minutes, status, booking_type,
       target_type, target_id, notes, confirmed_at, cancelled_at, cancellation_reason
FROM online_booking_booking
WHERE id = :booking_id AND hub_id = :hub_id AND is_deleted = 0;
