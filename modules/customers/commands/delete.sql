-- Soft-delete de cliente. Portado de CustomerService.delete_customer.
UPDATE customers_customer
SET is_deleted = 1, deleted_at = :now, is_active = 0,
    updated_by = :current_user_id, updated_at = :now
WHERE id = :customer_id AND hub_id = :hub_id;
