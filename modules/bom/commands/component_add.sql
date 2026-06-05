-- Añade una línea de componente a una BOM. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de BOMService.add_component.
-- Validaciones quantity>0 y la guarda de auto-referencia (sub_bom_id != bom_id) las
-- aplica el runtime/SDK antes de ejecutar; :sub_bom_id puede ser NULL (componente hoja).
INSERT INTO bom_component
  (id, hub_id, bom_id, component_ref, quantity, unit, scrap_pct, is_optional, sub_bom_id,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :bom_id, :component_ref, :quantity, :unit, :scrap_pct, :is_optional, :sub_bom_id,
   0, :current_user_id, :current_user_id, :now, :now);
