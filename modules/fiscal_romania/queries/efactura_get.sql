-- Una e-Factura por id (incluye el XML generado). Runtime inyecta :hub_id.
SELECT id, document_number, invoice_ref, document_type, supplier_cif, customer_cif,
       total_amount, vat_amount, status, upload_id, submission_date,
       anaf_response, error_code, xml_content, created_at
FROM fiscal_romania_efactura
WHERE id = :efactura_id AND hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
