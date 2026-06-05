-- Alta de periodo contable (abierto). Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de GeneralLedgerService.create_period. La validación de fechas
-- (end_date >= start_date) y el rechazo de name duplicado van al runtime/SDK
-- (índice uq_gl_period_hub_name).
INSERT INTO general_ledger_period
  (id, hub_id, name, start_date, end_date, status, closed_by_ref,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :start_date, :end_date, 'open', '',
   0, :current_user_id, :current_user_id, :now, :now);
