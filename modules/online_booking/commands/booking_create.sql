-- Alta de reserva online. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de BookingService.create_booking.
-- La generación de :booking_reference (BK-00001, contador atómico por hub), la validación
-- de fecha futura (min_advance_hours/max_advance_days) y la detección de doble reserva por
-- staff van a runtime — ver WASM-TODO.md. Aquí solo se inserta la fila ya validada.
INSERT INTO online_booking_booking
  (id, hub_id, booking_reference, customer_id, customer_name, customer_email,
   customer_phone, service_id, service_name, staff_id, staff_name,
   booking_date, booking_time, duration_minutes, status, booking_type,
   notes, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :booking_reference, :customer_id, :customer_name, :customer_email,
   :customer_phone, :service_id, :service_name, :staff_id, :staff_name,
   :booking_date, :booking_time, :duration_minutes, 'pending', :booking_type,
   :notes, 0, :current_user_id, :current_user_id, :now, :now);
