-- Actualización del PDF/A-3 + XML embebido de un ZUGFeRD. Lo invoca el handler WASM
-- (generate_pdf) con el xml_embedded compuesto y la ruta pdf_a3_path.
-- Runtime inyecta :current_user_id, :now.
UPDATE fiscal_germany_zugferd
SET pdf_a3_path = :pdf_a3_path,
    xml_embedded = :xml_embedded,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :zugferd_id AND hub_id = :hub_id AND is_deleted = 0;
