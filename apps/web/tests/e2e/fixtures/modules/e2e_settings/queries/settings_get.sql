-- hub#2511 — the read the settings screen runs. No row: this fixture has never saved anything, so
-- the screen paints the schema defaults (a FAILED read paints an error state instead).
SELECT 1 AS track_stock WHERE 1 = 0
