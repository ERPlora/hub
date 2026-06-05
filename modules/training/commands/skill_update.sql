-- Edición de habilidad. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de skill_edit.
UPDATE training_skill
SET name        = :name,
    category    = :category,
    description = :description,
    updated_by  = :current_user_id,
    updated_at  = :now
WHERE id = :skill_id AND hub_id = :hub_id AND is_deleted = 0;
