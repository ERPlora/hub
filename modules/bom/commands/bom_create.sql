-- Alta de BOM en estado draft. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de BOMService.create_bom. La unicidad de (hub_id, code) la garantiza el índice
-- uq_bom_hub_code. La BOM nace draft, no-default; los campos opcionales (version, notes)
-- traen default desde el schema.
INSERT INTO bom_bom
  (id, hub_id, code, name, product_ref, version, status, is_default,
   effective_from, effective_to, notes, approved_by_ref, approved_at,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :product_ref, :version, 'draft', 0,
   NULL, NULL, :notes, '', NULL,
   0, :current_user_id, :current_user_id, :now, :now);
