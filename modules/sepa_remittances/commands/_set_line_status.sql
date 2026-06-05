-- Helper interno invocado por el handler WASM (mark_processed / mark_rejected). Fija el
-- estado y motivo de rechazo de una línea concreta. Runtime inyecta :hub_id, :current_user_id, :now.
-- NO se invoca directamente desde la UI.
UPDATE sepa_remittances_line
SET status           = :status,
    rejection_reason = :rejection_reason,
    updated_by       = :current_user_id,
    updated_at       = :now
WHERE id = :line_id AND hub_id = :hub_id AND is_deleted = 0;
