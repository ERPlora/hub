-- Persistir la respuesta del operador a una pregunta. Runtime inyecta
-- :current_user_id, :now. Portado de SetupWizardService.answer_question.
UPDATE ai_setup_wizard_question
SET answer = :answer,
    answered_at = :now,
    updated_by = :current_user_id,
    updated_at = :now
WHERE id = :question_id AND hub_id = :hub_id AND is_deleted = 0;
