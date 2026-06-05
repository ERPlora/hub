-- Reservas online del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de BookingService.list_bookings. Los filtros :status y :booking_date son
-- opcionales ('' = sin filtro). El ordenado por fecha/hora desc replica el original.
SELECT id, booking_reference, customer_name, customer_email, customer_phone,
       service_name, staff_name, booking_date, booking_time, duration_minutes,
       status, booking_type, notes
FROM online_booking_booking
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
  AND (:booking_date = '' OR booking_date = :booking_date)
ORDER BY booking_date DESC, booking_time DESC;
