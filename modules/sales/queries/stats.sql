SELECT COUNT(*) AS count, COALESCE(SUM(total),0) AS total_revenue, COALESCE(AVG(total),0) AS avg_ticket
FROM sales_sale
WHERE hub_id = :hub_id AND is_deleted = 0 AND status = 'completed';
