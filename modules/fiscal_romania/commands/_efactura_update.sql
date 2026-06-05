-- Helper interno: aplica el resultado de una transición de e-Factura (generate_xml,
-- submit, validate). El handler WASM comprueba la guarda de estado y compone los
-- nuevos valores; aquí solo se persisten. Campos no cambiados se reescriben con su
-- valor actual (el handler los lee primero). Runtime inyecta :hub_id, :current_user_id, :now.
UPDATE fiscal_romania_efactura
SET status          = :status,
    xml_content     = :xml_content,
    upload_id       = :upload_id,
    submission_date = :submission_date,
    anaf_response   = :anaf_response,
    error_code      = :error_code,
    updated_by      = :current_user_id,
    updated_at      = :now
WHERE id = :efactura_id AND hub_id = :hub_id AND is_deleted = 0;
