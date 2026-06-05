-- Fija el estado de una cotización + totales recalculados. Comando interno invocado por
-- el handler WASM (convert_to_order, expire_old_quotes, update_quote_lines). El WASM ya
-- ha validado la transición y calculado :total_amount/:tax_amount. Runtime inyecta scope.
UPDATE quotes_quote
SET status = :status,
    total_amount = :total_amount,
    tax_amount = :tax_amount,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :quote_id AND hub_id = :hub_id AND is_deleted = 0;
