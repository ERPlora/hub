-- Detalle de un miembro del staff. Runtime inyecta :hub_id.
-- Portado de StaffService.get_staff_detail (la lista de servicios se obtiene aparte).
SELECT m.id, m.first_name, m.last_name,
       (m.first_name || ' ' || m.last_name) AS full_name,
       m.email, m.phone, m.photo, m.employee_id,
       m.role_id, r.name AS role_name, m.user_id,
       m.hire_date, m.termination_date, m.status,
       m.bio, m.specialties, m.is_bookable, m.color, m.booking_buffer,
       m.hourly_rate, m.commission_rate, m."order", m.notes
FROM staff_member m
LEFT JOIN staff_role r ON r.id = m.role_id AND r.is_deleted = 0
WHERE m.hub_id = :hub_id AND m.is_deleted = 0 AND m.id = :staff_id;
