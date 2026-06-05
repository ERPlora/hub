-- Config fiscal italiana (única) del hub. Portado de ItFiscalService.get_config.
-- Runtime inyecta :hub_id. Devuelve 0 o 1 fila.
SELECT id, partita_iva, codice_fiscale, company_name, sdi_environment,
       sdi_credentials_hash, default_codice_destinatario
FROM fiscal_italy_config
WHERE hub_id = :hub_id AND is_deleted = 0
LIMIT 1;
