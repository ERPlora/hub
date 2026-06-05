-- Sesiones de setup del hub, con filtro opcional por status. Runtime inyecta :hub_id.
-- Portado de SetupWizardService.list_sessions (orden por created_at desc).
-- :status = '' significa sin filtro. :limit acota el nº de filas.
SELECT id, session_number, business_type, industry_description, goals, pain_points,
       team_size, status, started_at, completed_at, recommended_modules,
       applied_modules, user_ref, notes, created_at
FROM ai_setup_wizard_session
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:status = '' OR status = :status)
ORDER BY created_at DESC
LIMIT :limit;
