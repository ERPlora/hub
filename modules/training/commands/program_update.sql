-- Edición de programa de formación. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de program_edit.
UPDATE training_program
SET name             = :name,
    description      = :description,
    duration_hours   = :duration_hours,
    is_mandatory     = :is_mandatory,
    category         = :category,
    provider         = :provider,
    cost             = :cost,
    max_participants = :max_participants,
    is_active        = :is_active,
    updated_by       = :current_user_id,
    updated_at       = :now
WHERE id = :program_id AND hub_id = :hub_id AND is_deleted = 0;
