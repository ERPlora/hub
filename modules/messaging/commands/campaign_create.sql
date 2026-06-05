-- Alta de campaña en borrador. Runtime inyecta :new_id, :hub_id, :current_user_id, :now.
-- Portado de CampaignCreate. El envío masivo (resolver destinatarios, encolar mensajes,
-- actualizar contadores) es batch → WASM/runtime, ver WASM-TODO (campaign.send).
INSERT INTO messaging_campaign
  (id, hub_id, name, description, channel, template_id, status,
   scheduled_at, total_recipients, sent_count, delivered_count, failed_count, target_filter,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :name, :description, :channel, :template_id, 'draft',
   :scheduled_at, 0, 0, 0, 0, :target_filter,
   0, :current_user_id, :current_user_id, :now, :now);
