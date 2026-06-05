-- Un programa de formación por id. Runtime inyecta :hub_id.
-- Portado de ProgramService.get (vista de detalle).
SELECT id, name, description, duration_hours, is_mandatory, category, provider,
       cost, max_participants, is_active
FROM training_program
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :program_id;
