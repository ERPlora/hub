-- Inscripciones de un programa (o todas si :program_id = ''). Runtime inyecta :hub_id.
-- Portado de program_enrollments. Filtro opcional por status (''=todos).
SELECT id, employee_id, employee_name, program_id, status, start_date,
       completion_date, expiry_date, score, certificate_url, notes
FROM training_employee_training
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:program_id = '' OR program_id = :program_id)
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC;
