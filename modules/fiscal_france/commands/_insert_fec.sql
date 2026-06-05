-- Helper (invocado por el handler WASM generate_fec): persiste los metadatos del export FEC.
-- El payload (CSV con delimitador '|' o XML) NO se persiste: lo devuelve el WASM inline.
-- La validación de periodo/formato y la serialización las hace el WASM — ver WASM-TODO.
-- Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
INSERT INTO fiscal_france_fec
  (id, hub_id, period_start, period_end, format_type, generated_at, total_entries,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :period_start, :period_end, :format_type, :now, :total_entries,
   0, :current_user_id, :current_user_id, :now, :now);
