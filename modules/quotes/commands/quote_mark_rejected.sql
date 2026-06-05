-- Marca una cotización enviada como rechazada. Portado de QuoteService.mark_rejected.
-- Guarda de estado: solo desde 'sent'. (El rastro de :reason en notes queda para WASM/Tier 1.)
UPDATE quotes_quote
SET status = 'rejected',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :quote_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'sent';
