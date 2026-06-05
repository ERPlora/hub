-- Alta de concepto de nómina (devengo o deducción). Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de ConceptService.create_concept. El enum de type lo
-- valida el JSON Schema (earning|deduction).
INSERT INTO payroll_concept
  (id, hub_id, name, type, is_percentage, amount, percentage, is_taxable,
   is_active, sort_order,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :type, :is_percentage, :amount, :percentage, :is_taxable,
   1, :sort_order,
   0, :current_user_id, :current_user_id, :now, :now);
