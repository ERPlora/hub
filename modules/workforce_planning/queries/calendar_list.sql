-- Entradas del calendario laboral (festivos/días especiales) del hub.
-- Runtime inyecta :hub_id. Filtros opcionales por rango de fechas (ISO YYYY-MM-DD).
SELECT id, date, name, calendar_type, region, is_working_day,
       pay_multiplier, recurring_yearly, notes
FROM workforce_planning_labor_calendar
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:date_from = '' OR date >= :date_from)
  AND (:date_to   = '' OR date <= :date_to)
ORDER BY date ASC;
