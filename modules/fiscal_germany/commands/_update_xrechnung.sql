-- Actualización de estado/payload de un XRechnung. Lo invoca el handler WASM tras
-- generate_xml / validate / submit. El WASM compone los nuevos valores (xml_content, status,
-- validation_errors como JSON o NULL, submission_date como ISO o NULL).
-- Runtime inyecta :current_user_id, :now.
UPDATE fiscal_germany_xrechnung
SET xml_content = :xml_content,
    status = :status,
    validation_errors = :validation_errors,
    submission_date = :submission_date,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :xrechnung_id AND hub_id = :hub_id AND is_deleted = 0;
