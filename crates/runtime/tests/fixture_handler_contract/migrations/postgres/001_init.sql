CREATE TABLE IF NOT EXISTS contract_rows (
  id TEXT NOT NULL,
  hub_id TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (hub_id, id)
);
