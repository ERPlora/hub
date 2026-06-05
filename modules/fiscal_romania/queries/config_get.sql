-- Configuración fiscal rumana del hub (una sola fila). Runtime inyecta :hub_id.
-- Portado de RoFiscalService.get_config.
SELECT id, company_cif, company_name, anaf_environment, api_key_hash,
       last_token_refresh_at
FROM fiscal_romania_config
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
