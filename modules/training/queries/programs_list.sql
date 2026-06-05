-- Programas de formación del hub (con filtros opcionales). Runtime inyecta :hub_id.
-- Portado de ProgramService.list_programs / program_list. Los binds opcionales usan ''/-1
-- como "sin filtro" (el SDK/UI los pasa siempre).
-- Los agregados enrolled_count/completion_rate (propiedades del modelo legacy) se calculan
-- en la UI o vía query separada; aquí devolvemos la cabecera del programa.
SELECT id, name, description, duration_hours, is_mandatory, category, provider,
       cost, max_participants, is_active
FROM training_program
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:search = '' OR name LIKE '%' || :search || '%')
  AND (:category = '' OR category = :category)
  AND (:is_mandatory = -1 OR is_mandatory = :is_mandatory)
  AND (:is_active = -1 OR is_active = :is_active)
ORDER BY name ASC;
