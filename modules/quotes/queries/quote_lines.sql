-- Líneas de una cotización (scope hub_id). Portado de _serialize_line (orden por creación).
SELECT id, quote_id, description, quantity, unit_price, discount_pct, tax_rate, line_total
FROM quotes_quote_line
WHERE quote_id = :quote_id AND hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC;
