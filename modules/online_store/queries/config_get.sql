-- Configuración (singleton) del escaparate del hub. Runtime inyecta :hub_id.
-- Portado de StoreService.get_store_config. La creación de la fila por defecto cuando
-- no existe (get-or-create) la hace el runtime/WASM — ver WASM-TODO. Aquí devolvemos
-- la fila viva (a lo sumo una) si existe.
SELECT id, store_name, domain, default_currency, language, is_published,
       theme, primary_color, logo_url
FROM online_store_config
WHERE hub_id = :hub_id AND is_deleted = 0
ORDER BY created_at ASC
LIMIT 1;
