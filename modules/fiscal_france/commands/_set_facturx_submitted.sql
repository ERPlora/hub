-- Helper (invocado por el handler WASM submit_facturx): transiciona a 'submitted' y fija
-- la fecha de envío. La guarda de estado (solo draft/generated) y la comprobación de que
-- el XML existe las hace el WASM — ver WASM-TODO. Runtime inyecta :current_user_id, :now.
UPDATE fiscal_france_facturx
SET status = 'submitted',
    submission_date = :submission_date,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :facturx_id AND hub_id = :hub_id AND is_deleted = 0;
