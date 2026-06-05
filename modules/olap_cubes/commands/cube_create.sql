-- Alta de cubo OLAP. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de OLAPService.create_cube. La validación de aggs de medidas (sum/avg/count/max/min),
-- de dimensiones/medidas no vacías y la unicidad de code la cubre el schema + el índice
-- ix_olap_cube_hub_code. :dimensions/:measures/:filters llegan ya serializados como JSON.
INSERT INTO olap_cubes_cube
  (id, hub_id, code, name, description, source_table,
   dimensions, measures, filters, is_active,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :source_table,
   :dimensions, :measures, :filters, 1,
   0, :current_user_id, :current_user_id, :now, :now);
