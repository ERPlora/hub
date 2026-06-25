-- Bindea `:status` y `:priority` DIRECTAMENTE, SIN COALESCE: depende de que el runtime
-- haya inyectado el `default` del JSON Schema para las claves ausentes.
INSERT INTO defaults_item (id, hub_id, name, status, priority)
VALUES (:new_id, :hub_id, :name, :status, :priority);
