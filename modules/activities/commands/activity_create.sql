-- Alta de actividad. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ActivityService.create_activity. La validación de enums (activity_type,
-- priority) y el parseo de scheduled_for los hace el JSON Schema / SDK; la nueva
-- actividad nace siempre en status='pending'.
INSERT INTO activities_activity
  (id, hub_id, activity_type, subject, description,
   related_entity_type, related_entity_ref, scheduled_for, completed_at,
   duration_minutes, assigned_to_ref, created_by_ref, status, priority,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :activity_type, :subject, :description,
   :related_entity_type, :related_entity_ref, :scheduled_for, NULL,
   NULL, :assigned_to_ref, :created_by_ref, 'pending', :priority,
   0, :current_user_id, :current_user_id, :now, :now);
