-- Helper interno: aplica la transición submit de un aviso e-Transport (draft → submitted,
-- fija uit_code + submitted_at). El handler WASM valida la guarda de estado. Runtime
-- inyecta :hub_id, :current_user_id, :now.
UPDATE fiscal_romania_etransport
SET status       = :status,
    uit_code     = :uit_code,
    submitted_at = :submitted_at,
    updated_by   = :current_user_id,
    updated_at   = :now
WHERE id = :etransport_id AND hub_id = :hub_id AND is_deleted = 0;
