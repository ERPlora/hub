-- Alta de bin dentro de una zona. Runtime inyecta :new_id, :hub_id,
-- :current_user_id, :now. Portado de LocationService.create_bin.
-- code es único dentro del almacén (uq_locations_bin_wh_code sobre
-- (hub_id, warehouse_id, code)). warehouse_id se denormaliza desde la zona: el
-- runtime lo resuelve leyendo la zona (locations.zones.list) antes de ejecutar y lo
-- pasa como :warehouse_id; el WC nunca lo deriva por su cuenta tocando otra tabla.
INSERT INTO locations_bin
  (id, hub_id, zone_id, warehouse_id, code, barcode, capacity,
   is_active, is_blocked, block_reason,
   is_deleted, created_by, updated_by, created_at, updated_at)
VALUES
  (:new_id, :hub_id, :zone_id, :warehouse_id, :code, :barcode, :capacity,
   1, 0, '',
   0, :current_user_id, :current_user_id, :now, :now);
