-- What a module's own settings screen asks so it can WARN (hub#1425): «you switched me on and I
-- cannot do a thing». It never reads `_module_capability_grants` — that table is a system table
-- (`migration_guard` forbids it); it binds the system param the runtime sounds.
SELECT :capabilities_granted AS can_sign;
