-- Alta de una definición de KPI. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de KPIService.create_kpi. La validación de enums (unit/kpi_type/aggregation/
-- target_direction) y el rechazo de code duplicado los cubre el schema + índice único
-- ix_kpi_hub_code. No hay lógica de cálculo aquí.
INSERT INTO kpis_kpi
  (id, hub_id, code, name, description, unit, kpi_type, aggregation, category,
   target_value, target_direction, critical_threshold, warning_threshold,
   is_active, owner_ref, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :code, :name, :description, :unit, :kpi_type, :aggregation, :category,
   :target_value, :target_direction, :critical_threshold, :warning_threshold,
   1, :owner_ref, 0, :current_user_id, :current_user_id, :now, :now);
