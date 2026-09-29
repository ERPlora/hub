-- hub#2359: v2 adds an INTEGER column (expand-only, ADR-0269). Its values are spaced so a TEXT
-- comparison and a NUMERIC one disagree ('100' sorts below '50' as text): if the engine does not
-- know `score` is numeric, a TEXT bound over it fails with `integer >= text` instead of filtering.
ALTER TABLE listshape_item ADD COLUMN score INTEGER NOT NULL DEFAULT 0;
UPDATE listshape_item SET score = 100 WHERE id = 'low';
UPDATE listshape_item SET score = 7 WHERE id = 'mid';
UPDATE listshape_item SET score = 60 WHERE id = 'high';
