-- Un registro de tiempo por id (scope hub_id). Portado de TimesheetService.get_time_entry.
SELECT id, employee_id, employee_name, date, start_time, end_time,
       duration_minutes, description, status, billable, project_name,
       client_name, hourly_rate_id, rate_amount, approved_by, approved_at,
       rejection_notes
FROM timesheets_time_entry
WHERE id = :entry_id AND hub_id = :hub_id AND is_deleted = 0;
