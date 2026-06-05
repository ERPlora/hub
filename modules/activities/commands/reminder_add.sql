-- Alta de recordatorio sobre una actividad existente.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ActivityService.add_reminder. La existencia de la actividad la valida el
-- runtime (FK activity_id) antes de insertar; nace con reminder_sent=0.
INSERT INTO activities_reminder
  (id, hub_id, activity_id, remind_at, reminder_sent,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :activity_id, :remind_at, 0,
   0, :current_user_id, :current_user_id, :now, :now);
