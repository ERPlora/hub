-- Actualiza la configuración (singleton) del escaparate. Runtime inyecta :current_user_id, :now.
-- Portado de StoreService.update_store_config (rama UPDATE: la fila ya existe).
-- El get-or-create (crear la fila por defecto si no existe) y la validación de campos
-- desconocidos van a WASM/runtime — ver WASM-TODO. La UI envía el conjunto completo de campos.
UPDATE online_store_config SET
  store_name       = :store_name,
  domain           = :domain,
  default_currency = :default_currency,
  language         = :language,
  is_published     = :is_published,
  theme            = :theme,
  primary_color    = :primary_color,
  logo_url         = :logo_url,
  updated_by       = :current_user_id,
  updated_at       = :now
WHERE id = :config_id AND hub_id = :hub_id AND is_deleted = 0;
