-- Alta de una línea transfronteriza para el Esterometro.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de ItFiscalService.record_esterometro_entry. La validación de enums
-- (transaction_type), país ISO-2, mes 1..12 y año >= 2000 la garantiza el JSON Schema;
-- counterparty_country se normaliza en mayúsculas en el SDK/UI antes de enviar.
INSERT INTO fiscal_italy_esterometro_entry
  (id, hub_id, period_year, period_month, transaction_type, counterparty_country,
   counterparty_vat_id, total_amount, transaction_date, document_ref, status,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :period_year, :period_month, :transaction_type, :counterparty_country,
   :counterparty_vat_id, :total_amount, :transaction_date, :document_ref, 'pending',
   0, :current_user_id, :current_user_id, :now, :now);
