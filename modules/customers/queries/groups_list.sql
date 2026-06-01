-- Grupos del hub con nº de clientes vinculados. Portado de GroupService.list_groups.
SELECT g.id, g.name, g.description, g.discount_percent, g.color, g.sort_order, g.is_active,
       (SELECT COUNT(*) FROM customers_customer_groups cg
        JOIN customers_customer c ON c.id = cg.customer_id
        WHERE cg.group_id = g.id AND c.is_deleted = 0) AS customer_count
FROM customers_customergroup g
WHERE g.hub_id = :hub_id AND g.is_deleted = 0 AND g.is_active = 1
ORDER BY g.sort_order ASC, g.name ASC;
