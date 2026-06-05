-- Alta de habilidad. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de SkillService.create_skill.
INSERT INTO training_skill
  (id, hub_id, name, category, description, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :category, :description, 1,
   0, :current_user_id, :current_user_id, :now, :now);
