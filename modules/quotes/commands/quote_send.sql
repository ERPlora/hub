-- Marca una cotización draft como enviada. Portado de QuoteService.send_quote.
-- Guarda de estado en el WHERE: solo transiciona si está en 'draft'.
-- (El rastro de :email_to en notes y el transporte de email quedan para Tier 1 — ver WASM-TODO.)
UPDATE quotes_quote
SET status = 'sent',
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :quote_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
