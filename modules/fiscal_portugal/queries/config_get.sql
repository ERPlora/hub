-- Configuración fiscal portuguesa del hub (única por hub). Runtime inyecta :hub_id.
-- Portado de PtFiscalService.get_config. Nunca se devuelve el hash de credenciales en claro
-- como secreto: at_credentials_hash es ya un digest. Devuelve 0 o 1 fila.
SELECT id, nif, company_name, at_environment, at_credentials_hash,
       serie_certification_code, software_certification_number
FROM fiscal_portugal_config
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
