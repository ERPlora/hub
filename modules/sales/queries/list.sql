SELECT id, sale_number, status, total, tax_amount, payment_method_name,
       customer_name, channel, created_at
FROM sales_sale
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at DESC
LIMIT 100;
