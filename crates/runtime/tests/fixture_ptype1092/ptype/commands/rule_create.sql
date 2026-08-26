-- Declarative INSERT binding `:rate`, whose JSON Schema declares `"type": "number"`.
INSERT INTO ptype_rule (id, hub_id, rate)
VALUES (:new_id, :hub_id, :rate)
