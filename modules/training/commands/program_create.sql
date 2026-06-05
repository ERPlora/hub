-- Alta de programa de formación. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ProgramService.create_program.
INSERT INTO training_program
  (id, hub_id, name, description, duration_hours, is_mandatory, category, provider,
   cost, max_participants, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :duration_hours, :is_mandatory, :category, :provider,
   :cost, :max_participants, 1,
   0, :current_user_id, :current_user_id, :now, :now);
