-- invoice_series · migration 002 — the validity window cannot end before it starts (invoice_series#8).
--
-- `start_date` / `end_date` are the optional ISO-8601 window of a series (TEXT, ADR-0007: dates are
-- text and compare lexicographically). `series.update` refuses an inverted window in its WHERE (so
-- the runtime's `expect_rows` gate turns it into the translatable domain error
-- `invoice_series.series_update_rejected`); this CHECK is the last line: whatever door a row comes
-- through (a future command, a private operation of the WASM handler, a manual fix), the invariant
-- holds. Either bound may be NULL (open-ended window); a one-day window (start = end) is valid.
--
-- `NOT VALID`: append-only and safe on a hub that already has rows — Postgres enforces the CHECK
-- for every INSERT/UPDATE from now on but does not scan the existing rows, so a legacy row cannot
-- make the deploy's `migrate` abort. A later `VALIDATE CONSTRAINT` is optional housekeeping.
ALTER TABLE invoice_series_series
  ADD CONSTRAINT ck_invoice_series_validity
  CHECK (start_date IS NULL OR end_date IS NULL OR start_date <= end_date) NOT VALID;
