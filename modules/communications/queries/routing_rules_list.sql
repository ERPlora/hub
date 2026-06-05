-- Reglas de enrutado del hub, por prioridad ascendente (menor gana). El runtime inyecta :hub_id.
SELECT id, group_id, name, priority, is_active, conditions,
       auto_assign_to_id, auto_label, auto_priority
FROM communications_routing_rule
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY priority ASC, name ASC;
