-- Datos crudos de la matriz de habilidades: filas empleado×habilidad. Runtime inyecta :hub_id.
-- Portado de skills_matrix. La UI pivota estas filas a una rejilla {empleado:{skill:nivel}}.
-- (El WC NUNCA toca la BD: solo transforma este resultado plano.)
SELECT id, employee_id, employee_name, skill_id, proficiency_level, acquired_date, notes
FROM training_employee_skill
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY employee_name ASC, skill_id ASC;
