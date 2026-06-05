-- Un documento XRechnung por id (scope hub_id). Incluye xml_content y validation_errors.
-- Lo usa el handler WASM (a través del runtime) para generar XML / validar / enviar.
SELECT id, document_number, invoice_ref, supplier_ust_id, customer_leitweg_id,
       total_netto, total_steuer, total_brutto, status, xml_content,
       validation_errors, submission_date, created_at
FROM fiscal_germany_xrechnung
WHERE id = :xrechnung_id AND hub_id = :hub_id AND is_deleted = 0;
