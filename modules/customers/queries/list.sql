-- Lista de clientes del hub (más recientes primero). Portado de CustomerService.list_customers.
-- Filtros de búsqueda/lifecycle/grupo/tag se aplican en UI/SDK (Tier 0/1).
SELECT id, name, email, phone, tax_id, company_name, lifecycle_stage, source,
       is_active, total_purchases, total_spent, last_purchase_date
FROM customers_customer
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY name ASC
LIMIT 100;
