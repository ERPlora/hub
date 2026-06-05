-- Helper interno invocado por el handler WASM (create_direct_debit / create_credit_transfer).
-- Inserta una línea de remesa ya validada (mandato activo / contraparte resuelta) y con su
-- end_to_end_id calculado. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- :mandate_id puede ser NULL (transferencias). NO se invoca directamente desde la UI.
INSERT INTO sepa_remittances_line
  (id, hub_id, remittance_id, mandate_id, counterparty_name, counterparty_iban,
   amount, concept, end_to_end_id, status, rejection_reason,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :remittance_id, :mandate_id, :counterparty_name, :counterparty_iban,
   :amount, :concept, :end_to_end_id, 'pending', '',
   0, :current_user_id, :current_user_id, :now, :now);
