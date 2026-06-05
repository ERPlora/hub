-- Solicitudes de ausencia del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- :staff_id = '' sin filtro; :status = '' sin filtro.
SELECT t.id, t.staff_id,
       (m.first_name || ' ' || m.last_name) AS staff_name,
       t.leave_type, t.start_date, t.end_date, t.is_full_day,
       t.start_time, t.end_time, t.status, t.approved_by, t.approved_at,
       t.reason, t.notes
FROM staff_time_off t
JOIN staff_member m ON m.id = t.staff_id AND m.is_deleted = 0
WHERE t.hub_id = :hub_id AND t.is_deleted = 0
  AND (:staff_id = '' OR t.staff_id = :staff_id)
  AND (:status = '' OR t.status = :status)
ORDER BY t.start_date DESC;
