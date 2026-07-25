-- Fixture: ALTER aditivo que DEPENDE de 001 (si se aplica solo, falla: tabla inexistente).
ALTER TABLE migunion_partial_items ADD COLUMN note TEXT;
