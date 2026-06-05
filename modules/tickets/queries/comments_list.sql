-- Comentarios hilados de un ticket, en orden cronológico. Runtime inyecta :hub_id.
-- Portado de TicketService.get_ticket (rama include_comments).
SELECT id, ticket_id, author_ref, comment_text, is_internal, created_at
FROM tickets_comment
WHERE hub_id = :hub_id AND is_deleted = 0
  AND ticket_id = :ticket_id
ORDER BY created_at ASC;
