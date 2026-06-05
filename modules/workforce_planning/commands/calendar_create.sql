-- Alta de entrada del calendario laboral. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de LaborCalendarCreate. El uq (hub, date, calendar_type, region) lo garantiza el índice.
INSERT INTO workforce_planning_labor_calendar
  (id, hub_id, date, name, calendar_type, region, is_working_day,
   pay_multiplier, recurring_yearly, notes,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :date, :name, :calendar_type, :region, :is_working_day,
   :pay_multiplier, :recurring_yearly, :notes,
   0, :current_user_id, :current_user_id, :now, :now);
