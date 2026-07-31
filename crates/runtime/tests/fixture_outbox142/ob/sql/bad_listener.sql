-- Intencionadamente ROTO: referencia una columna que no existe → el listener
-- falla SIEMPRE al ejecutarse. Es el "listener venenoso" del síntoma (a) de hub#142:
-- antes del fix abortaba la entrega a sus hermanos; ahora se difiere solo él.
INSERT INTO ob_log (no_such_column) VALUES (1);
