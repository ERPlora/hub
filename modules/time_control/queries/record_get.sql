-- Un fichaje por id (scope hub_id). Portado de TimeControlService.get_clock_record.
SELECT id, employee_id, employee_name, timestamp, record_type, method,
       latitude, longitude, address, workplace_id, is_within_geofence,
       ip_address, user_agent, notes
FROM time_control_clock_record
WHERE id = :clock_record_id AND hub_id = :hub_id AND is_deleted = 0;
