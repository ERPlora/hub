-- Un cliente por id (scope hub_id). Portado de CustomerService.get_customer.
SELECT id, name, email, phone, tax_id, address, city, postal_code, country, avatar,
       notes, is_active, lifecycle_stage, source, company_name, birthday, anniversary,
       preferred_channel, marketing_consent, consent_date,
       total_purchases, total_spent, last_purchase_date, created_at, updated_at
FROM customers_customer
WHERE id = :customer_id AND hub_id = :hub_id AND is_deleted = 0;
