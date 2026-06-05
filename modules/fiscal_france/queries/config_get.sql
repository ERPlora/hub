-- Configuración fiscal francesa del hub (una sola fila en la práctica). Runtime inyecta :hub_id.
-- Portado de FrFiscalService.get_config. Nunca se devuelve credencial en claro, solo el hash.
SELECT id, siret, siren, company_name, chorus_pro_environment, chorus_credentials_hash
FROM fiscal_france_config
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC
LIMIT 1;
