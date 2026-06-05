-- Grupos de enrutado activos del hub. El runtime inyecta :hub_id.
SELECT id, name, description, icon, color, is_active, is_default, is_system, source
FROM communications_group
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY is_default DESC, name ASC;
