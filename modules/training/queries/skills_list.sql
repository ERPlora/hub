-- Habilidades activas del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de SkillService.list_skills / skill_list (active_only por defecto, orden por name).
-- El employee_count (propiedad agregada del modelo legacy) se resuelve en la UI/query aparte.
SELECT id, name, category, description, is_active
FROM training_skill
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
  AND (:search = '' OR name LIKE '%' || :search || '%')
  AND (:category = '' OR category = :category)
ORDER BY name ASC;
