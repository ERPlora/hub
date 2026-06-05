-- Un documento ZUGFeRD por id (scope hub_id). Lo usa el handler WASM (vía runtime)
-- para generar el PDF/A-3 + XML embebido.
SELECT id, document_number, invoice_ref, supplier_ust_id, customer_name,
       total_netto, total_brutto, profile, pdf_a3_path, xml_embedded, created_at
FROM fiscal_germany_zugferd
WHERE id = :zugferd_id AND hub_id = :hub_id AND is_deleted = 0;
