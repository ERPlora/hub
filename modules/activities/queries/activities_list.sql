-- Lista de actividades del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de ActivityService.list_activities. Los binds opcionales usan '' = sin filtro.
SELECT id, activity_type, subject, description,
       related_entity_type, related_entity_ref,
       scheduled_for, completed_at, duration_minutes,
       assigned_to_ref, created_by_ref, status, priority, created_at
FROM activities_activity
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:activity_type       = '' OR activity_type       = :activity_type)
  AND (:status              = '' OR status              = :status)
  AND (:related_entity_type = '' OR related_entity_type = :related_entity_type)
  AND (:related_entity_ref  = '' OR related_entity_ref  = :related_entity_ref)
  AND (:assigned_to         = '' OR assigned_to_ref     = :assigned_to)
ORDER BY created_at DESC
LIMIT :limit;
