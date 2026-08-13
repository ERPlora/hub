-- Its OWN counter table: since hub#633 a module's command SQL may only write tables under its
-- own prefix, so the sibling cannot log into `ob_log` anymore (which was, ironically, exactly
-- the cross-module write the gate exists to refuse).
CREATE TABLE ob2_log (
  listener TEXT PRIMARY KEY,
  runs     INTEGER NOT NULL DEFAULT 0
);
