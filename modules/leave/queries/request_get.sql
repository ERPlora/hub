-- Detalle de una solicitud de ausencia. Runtime inyecta :hub_id.
-- Portado de LeaveService.get_request.
SELECT r.id, r.employee_id, r.employee_name, r.leave_type_id,
       t.name AS leave_type_name, r.start_date, r.end_date, r.days_count,
       r.is_half_day, r.half_day_period, r.status, r.reason,
       r.approved_by, r.approved_at, r.rejection_reason, r.notes
FROM leave_request r
LEFT JOIN leave_type t ON t.id = r.leave_type_id AND t.hub_id = r.hub_id
WHERE r.hub_id = :hub_id AND r.is_deleted = 0 AND r.id = :request_id;
