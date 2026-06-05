-- Detalle de un ticket por id. Runtime inyecta :hub_id.
-- Portado de TicketService.get_ticket (los comentarios se piden con tickets.comments.list).
SELECT id, ticket_number, subject, description,
       customer_name, customer_email, customer_phone,
       status, priority, category,
       assigned_to_ref, created_by_ref, sla_id,
       opened_at, first_response_at, resolved_at, closed_at,
       satisfaction_rating, created_at
FROM tickets_ticket
WHERE id = :ticket_id AND hub_id = :hub_id AND is_deleted = 0;
