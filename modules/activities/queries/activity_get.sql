-- Detalle de una actividad. Runtime inyecta :hub_id. Portado de ActivityService.get_activity.
-- Los recordatorios se obtienen aparte vía activities.reminders.list (:activity_id).
SELECT id, activity_type, subject, description,
       related_entity_type, related_entity_ref,
       scheduled_for, completed_at, duration_minutes,
       assigned_to_ref, created_by_ref, status, priority, created_at
FROM activities_activity
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :activity_id;
