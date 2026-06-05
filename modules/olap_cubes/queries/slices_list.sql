-- Slices cacheados de un cubo. Runtime inyecta :hub_id.
-- Filtro opcional por cubo (:cube_id = '' = todos). Orden por fecha de cómputo descendente.
-- La lectura puntual con incremento de hit_count y expiración va a WASM (cache.get) — ver WASM-TODO.
SELECT id, cube_id, slice_key, computed_at, expires_at, hit_count
FROM olap_cubes_cached_slice
WHERE hub_id = :hub_id AND is_deleted = 0
  AND (:cube_id = '' OR cube_id = :cube_id)
ORDER BY computed_at DESC;
