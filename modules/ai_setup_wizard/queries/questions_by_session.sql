-- Preguntas de una sesión, ordenadas por question_order. Runtime inyecta :hub_id.
-- Portado del include_questions de SetupWizardService.get_session.
SELECT id, session_id, question_order, question_type, question_text,
       options, answer, answered_at
FROM ai_setup_wizard_question
WHERE hub_id = :hub_id AND is_deleted = 0
  AND session_id = :session_id
ORDER BY question_order ASC;
