-- Alta de cliente. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CustomerService.create_customer (campos base; M2M groups/tags vía handler WASM).
INSERT INTO customers_customer
  (id, hub_id, name, email, phone, tax_id, address, city, postal_code, country, avatar,
   notes, is_active, lifecycle_stage, source, company_name, birthday, anniversary,
   preferred_channel, marketing_consent, consent_date, total_purchases, total_spent,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :email, :phone, :tax_id, :address, :city, :postal_code, :country, :avatar,
   :notes, 1, :lifecycle_stage, :source, :company_name, :birthday, :anniversary,
   :preferred_channel, :marketing_consent, :consent_date, 0, 0,
   0, :current_user_id, :current_user_id, :now, :now);
