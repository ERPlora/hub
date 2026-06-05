-- Lista de cotizaciones del hub. Runtime inyecta :hub_id.
-- Portado de QuoteService.list_quotes (filtro opcional por estado; orden por creación desc).
-- El filtro de :status vacío => '' devuelve todas (patrón "todo o coincidencia").
SELECT id, quote_number, status, customer_name, customer_email, customer_tax_id,
       issue_date, valid_until, total_amount, tax_amount
FROM quotes_quote
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT 50;
