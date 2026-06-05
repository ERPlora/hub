-- Envío de factura Chorus Pro: draft → uploaded con upload_id placeholder.
-- Portado de FrFiscalService.submit_chorus_invoice. La guarda "solo draft" va en el WHERE
-- (status='draft'): si no está en draft, 0 filas afectadas y el runtime devuelve no-op/error.
-- El upload_id real lo devolvería la API de Chorus Pro; aquí es 'PENDING-<num>'.
-- Runtime inyecta :current_user_id, :now.
UPDATE fiscal_france_chorus
SET status = 'uploaded',
    upload_id = 'PENDING-' || document_number,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :chorus_id AND hub_id = :hub_id AND is_deleted = 0 AND status = 'draft';
