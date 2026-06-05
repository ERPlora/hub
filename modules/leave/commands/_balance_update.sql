-- Primitiva interna: actualiza entitled_days/carried_over de un saldo existente (rama
-- "ya existía" del upsert de set_balance). used_days/pending_days NO se tocan aquí
-- (son rollups del workflow). COALESCE para parches parciales. Runtime inyecta binds.
UPDATE leave_balance
SET entitled_days = COALESCE(:entitled_days, entitled_days),
    carried_over  = COALESCE(:carried_over, carried_over),
    employee_name = COALESCE(:employee_name, employee_name),
    updated_by    = :current_user_id,
    updated_at    = :now
WHERE hub_id = :hub_id AND is_deleted = 0
  AND employee_id = :employee_id AND leave_type_id = :leave_type_id AND year = :year;
