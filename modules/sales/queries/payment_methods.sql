SELECT id, name, type, icon, opens_cash_drawer, requires_change, sort_order
FROM sales_payment_method
WHERE hub_id = :hub_id AND is_deleted = 0 AND is_active = 1
ORDER BY sort_order ASC, name ASC;
