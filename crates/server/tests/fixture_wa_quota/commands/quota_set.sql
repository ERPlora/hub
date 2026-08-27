-- Espejo de `commands/quota_set.sql` de ERPlora/whatsapp_inbox: el ÚNICO escritor del medidor de
-- la capa gratuita. Siembra la fila singleton (la ingesta no espera a que nadie abra los ajustes)
-- y en conflicto mueve solo el medidor y el sello de auditoría: sobrescribir los campos de la
-- pantalla haría que un cambio de plan borrase el saludo del comerciante.
INSERT INTO whatsapp_inbox_settings
  (id, hub_id, free_tier_monthly_limit, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :monthly_limit, 0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT(hub_id) DO UPDATE SET
   free_tier_monthly_limit = excluded.free_tier_monthly_limit,
   updated_by              = :current_user_id,
   updated_at              = :now;
