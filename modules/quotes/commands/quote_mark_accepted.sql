-- Marca una cotización enviada como aceptada. Portado de QuoteService.mark_accepted.
-- Guarda de estado: solo desde 'sent'.
UPDATE quotes_quote
SET status = 'accepted',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :quote_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'sent';
