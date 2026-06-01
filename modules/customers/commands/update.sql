-- Edición de cliente (la UI envía el conjunto completo de campos editables, Tier 0/1).
-- Portado de CustomerService.update_customer.
UPDATE customers_customer SET
  name = :name, email = :email, phone = :phone, tax_id = :tax_id,
  address = :address, city = :city, postal_code = :postal_code, country = :country,
  notes = :notes, lifecycle_stage = :lifecycle_stage, source = :source,
  company_name = :company_name, birthday = :birthday, anniversary = :anniversary,
  preferred_channel = :preferred_channel, marketing_consent = :marketing_consent,
  is_active = :is_active, updated_by = :current_user_id, updated_at = :now
WHERE id = :customer_id AND hub_id = :hub_id AND is_deleted = 0;
