-- Una habilidad por id. Runtime inyecta :hub_id.
-- Portado de ProgramService.get_skill.
SELECT id, name, category, description, is_active
FROM training_skill
WHERE hub_id = :hub_id AND is_deleted = 0 AND id = :skill_id;
