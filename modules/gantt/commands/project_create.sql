-- Alta de proyecto. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de GantService.create_project. La validación de status (enum) y el parseo de
-- fechas los aplica el schema/runtime; progress_pct arranca en 0.
INSERT INTO gantt_project
  (id, hub_id, name, description, start_date, end_date, status, color,
   owner_ref, progress_pct, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :start_date, :end_date, :status, :color,
   :owner_ref, 0, 0, :current_user_id, :current_user_id, :now, :now);
