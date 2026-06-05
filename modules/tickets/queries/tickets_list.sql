-- Lista de tickets del hub con filtros opcionales. Runtime inyecta :hub_id.
-- Portado de TicketService.list_tickets. Los binds de filtro deben pasarse siempre
-- (cadena vacía = sin filtro). El filtro por customer_name es subcadena (LIKE).
SELECT id, ticket_number, subject, description,
       customer_name, customer_email, customer_phone,
       status, priority, category,
       assigned_to_ref, created_by_ref, sla_id,
       opened_at, first_response_at, resolved_at, closed_at,
       satisfaction_rating, created_at
FROM tickets_ticket
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status        = '' OR status   = :status)
  AND (:priority      = '' OR priority = :priority)
  AND (:assigned_to   = '' OR assigned_to_ref = :assigned_to)
  AND (:customer_name = '' OR customer_name LIKE '%' || :customer_name || '%')
ORDER BY created_at DESC
LIMIT :limit;
