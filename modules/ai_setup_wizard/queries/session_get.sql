-- Detalle de una sesión de setup. Runtime inyecta :hub_id.
-- Portado de SetupWizardService.get_session (cabecera; preguntas y recomendaciones
-- se obtienen con las queries questions_by_session / recommendations_by_session).
SELECT id, session_number, business_type, industry_description, goals, pain_points,
       team_size, status, started_at, completed_at, recommended_modules,
       applied_modules, user_ref, notes, created_at
FROM ai_setup_wizard_session
WHERE hub_id = :hub_id AND is_deleted = 0
  AND id = :session_id;
