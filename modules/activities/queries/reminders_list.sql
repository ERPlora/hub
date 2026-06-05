-- Recordatorios de una actividad. Runtime inyecta :hub_id.
-- Portado de la lectura de reminders en ActivityService.get_activity.
SELECT id, activity_id, remind_at, reminder_sent
FROM activities_reminder
WHERE hub_id = :hub_id AND is_deleted = 0 AND activity_id = :activity_id
ORDER BY remind_at ASC;
