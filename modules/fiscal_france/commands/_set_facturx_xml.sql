-- Helper (invocado por el handler WASM generate_facturx_xml): persiste el XML ZUGFeRD
-- generado y, si estaba en draft, transiciona a 'generated'. El XML lo compone el WASM
-- (serialización UN/CEFACT Cross-Industry Invoice) — ver WASM-TODO.
-- Runtime inyecta :current_user_id, :now. :new_status lo decide el WASM (generated o el actual).
UPDATE fiscal_france_facturx
SET xml_zugferd_content = :xml_zugferd_content,
    status = :new_status,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :facturx_id AND hub_id = :hub_id AND is_deleted = 0;
