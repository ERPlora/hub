-- Alta de mandato SEPA. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de SepaService.create_mandate. La unicidad (hub_id, mandate_id) la garantiza el
-- índice uq_sepa_mandate_hub_mandate_id; la validación de scheme (CORE|B2B) va en el JSON Schema.
INSERT INTO sepa_remittances_mandate
  (id, hub_id, mandate_id, debtor_name, debtor_iban, debtor_bic, creditor_id,
   signed_date, status, scheme, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :mandate_id, :debtor_name, :debtor_iban, :debtor_bic, :creditor_id,
   :signed_date, 'active', :scheme, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
