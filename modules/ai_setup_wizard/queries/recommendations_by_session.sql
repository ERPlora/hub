-- Recomendaciones de una sesión. Runtime inyecta :hub_id.
-- Portado del include_recommendations de SetupWizardService.get_session.
SELECT id, session_id, category, title, description, priority,
       is_applied, applied_at, related_module_id
FROM ai_setup_wizard_recommendation
WHERE hub_id = :hub_id AND is_deleted = 0
  AND session_id = :session_id
ORDER BY priority DESC, created_at ASC;
