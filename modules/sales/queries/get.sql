SELECT id, sale_number, status, subtotal, tax_amount, tax_breakdown,
       discount_amount, discount_percent, total, payment_method_name,
       amount_tendered, change_due, customer_name, notes, channel, created_at
FROM sales_sale
WHERE id = :sale_id AND hub_id = :hub_id AND is_deleted = 0;
