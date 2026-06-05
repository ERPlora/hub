-- Lista de SLAs configurados para el hub. Runtime inyecta :hub_id.
-- Portado de TicketService.list_slas. active_only filtra los vigentes ('' = todos).
SELECT id, name, description, priority,
       response_time_hours, resolution_time_hours, is_active
FROM tickets_sla
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:active_only = '' OR is_active = 1)
ORDER BY priority ASC, name ASC;
