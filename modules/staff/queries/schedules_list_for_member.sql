-- Horarios de un miembro del staff. Runtime inyecta :hub_id.
-- Portado de routes.staff_schedules. Las working_hours se cargan por horario aparte si hace falta.
SELECT s.id, s.staff_id, s.name, s.is_default,
       s.effective_from, s.effective_until, s.is_active
FROM staff_schedule s
WHERE s.hub_id = :hub_id AND s.is_deleted = 0 AND s.staff_id = :staff_id
ORDER BY s.is_default DESC, s.name ASC;
