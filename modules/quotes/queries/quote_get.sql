-- Una cotización por id (scope hub_id). Portado de QuoteService.get_quote (cabecera).
-- Las líneas se piden aparte con quotes.quotes.lines.
SELECT id, quote_number, status, customer_name, customer_email, customer_tax_id,
       issue_date, valid_until, total_amount, tax_amount, notes, terms_conditions
FROM quotes_quote
WHERE id = :quote_id AND hub_id = :hub_id AND is_deleted = 0;
