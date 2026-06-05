-- Config fiscal alemana (única) del hub. Runtime inyecta :hub_id.
-- Portado de DeFiscalService.get_config (devuelve la primera, o vacío).
SELECT id, ust_id, steuernummer, company_name, leitweg_id_default, xrechnung_environment
FROM fiscal_germany_config
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC
LIMIT 1;
