-- Actividades pendientes programadas para hoy. Runtime inyecta :hub_id.
-- Portado de ActivityService.list_pending_today. El rango [inicio_dia, inicio_dia_siguiente)
-- lo calcula el SDK/runtime y se pasa como :day_start / :day_end (ISO datetime).
SELECT id, activity_type, subject, description,
       related_entity_type, related_entity_ref,
       scheduled_for, completed_at, duration_minutes,
       assigned_to_ref, created_by_ref, status, priority, created_at
FROM activities_activity
WHERE hub_id = :hub_id AND is_deleted = 0
  AND status = 'pending'
  AND scheduled_for >= :day_start
  AND scheduled_for <  :day_end
  AND (:assigned_to = '' OR assigned_to_ref = :assigned_to)
ORDER BY scheduled_for ASC;
