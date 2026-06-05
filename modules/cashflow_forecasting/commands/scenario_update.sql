-- Actualización de un escenario. Runtime inyecta :hub_id, :current_user_id, :now.
-- Portado de CashflowService.update_scenario. Los binds opcionales se pasan SIEMPRE:
-- el patrón (:x = '' OR ...) deja el valor previo si el bind viene vacío.
-- name/description/scenario_type/currency/parameters → '' = no cambia;
-- opening_balance → bind numérico (NULL = no cambia); is_active → '' = no cambia.
UPDATE cashflow_forecasting_scenario
SET name            = CASE WHEN :name = ''            THEN name            ELSE :name END,
    description     = CASE WHEN :description = ''     THEN description     ELSE :description END,
    scenario_type   = CASE WHEN :scenario_type = ''   THEN scenario_type   ELSE :scenario_type END,
    currency        = CASE WHEN :currency = ''        THEN currency        ELSE :currency END,
    parameters      = CASE WHEN :parameters = ''      THEN parameters      ELSE :parameters END,
    opening_balance = CASE WHEN :opening_balance IS NULL THEN opening_balance ELSE :opening_balance END,
    is_active       = CASE WHEN :is_active = ''       THEN is_active       ELSE CAST(:is_active AS INTEGER) END,
    updated_by      = :current_user_id,
    updated_at      = :now
WHERE id = :scenario_id AND hub_id = :hub_id AND is_deleted = 0;
