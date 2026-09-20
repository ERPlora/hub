-- Mirror of `commands/quota_set.sql` in ERPlora/whatsapp_inbox after whatsapp_inbox#155: the same
-- single writer of the meter, now carrying the spend the platform counted next to the cap.
--
-- `COALESCE(:monthly_usage, …)` is the half that matters for this fixture: a tick that knows the
-- cap but not the spend must leave the spend it already had, never reset it to zero. The hub only
-- omits the key, so the runtime binds it as NULL.
INSERT INTO whatsapp_inbox_settings
  (id, hub_id, free_tier_monthly_limit, monthly_usage, is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :monthly_limit, COALESCE(:monthly_usage, 0), 0, :current_user_id, :current_user_id, :now, :now)
ON CONFLICT(hub_id) DO UPDATE SET
   free_tier_monthly_limit = excluded.free_tier_monthly_limit,
   monthly_usage           = COALESCE(:monthly_usage, whatsapp_inbox_settings.monthly_usage),
   updated_by              = :current_user_id,
   updated_at              = :now;
