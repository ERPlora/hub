-- Helper interno invocado por el handler WASM. Persiste cabecera de remesa: totales
-- recalculados, estado, xml_content, generated_at, notes. El WASM pasa los valores ya
-- calculados (total_amount/total_count/xml/status). Runtime inyecta :hub_id, :current_user_id, :now.
-- NO se invoca directamente desde la UI.
UPDATE sepa_remittances_remittance
SET status       = :status,
    total_amount = :total_amount,
    total_count  = :total_count,
    xml_content  = :xml_content,
    generated_at = :generated_at,
    notes        = :notes,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :remittance_id AND hub_id = :hub_id AND is_deleted = 0;
