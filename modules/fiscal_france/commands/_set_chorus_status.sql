-- Helper (invocado por el handler WASM update_chorus_status): aplica el nuevo estado Chorus Pro
-- y el anomaly_code resultante. La validación del estado (under_review|accepted|rejected|paid),
-- la guarda "no draft" y la lógica del anomaly_code (set en rejected, clear en accepted/paid)
-- las hace el WASM — ver WASM-TODO. Runtime inyecta :current_user_id, :now.
UPDATE fiscal_france_chorus
SET status = :new_status,
    anomaly_code = :anomaly_code,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :chorus_id AND hub_id = :hub_id AND is_deleted = 0;
