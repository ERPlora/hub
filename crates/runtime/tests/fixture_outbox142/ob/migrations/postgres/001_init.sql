-- Fixture minimal para la regresión hub#142: una sola tabla contador por listener.
CREATE TABLE ob_log (
  listener TEXT PRIMARY KEY,
  runs     INTEGER NOT NULL DEFAULT 0
);
