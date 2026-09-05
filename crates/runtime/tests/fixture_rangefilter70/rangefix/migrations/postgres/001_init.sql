-- verifactu#70 fixture: a `range` filter over an INSTANT column (`happened_at`) next to one
-- over a bare CALENDAR-DATE column (`logged_on`) — both TEXT, the same shape every module in
-- production stores these in (`verifactu_event.timestamp`, `verifactu_contingency
-- .next_attempt_at`, `verifactu_aeat_record.query_timestamp` are all TEXT ISO-8601; a native
-- TIMESTAMPTZ column does not reproduce the bug at all — `>=`/`<=` against a bare-date bound
-- fail to PREPARE with `42883 operator does not exist`, not the silent empty page the issue
-- describes). Same day, two different STRING shapes — the bug and its regression guard live on
-- the same table on purpose.
--
-- hub#1542 adds the other two column KINDS a `range` filter is declared over in the published
-- catalogue, because the fix has to serve both from the same bound and they pull in opposite
-- directions:
--   * `priority` INTEGER — the numeric shape (`pricing.rules.priority`, `inventory.products
--     .stock`, `tables.sessions.guests_count`). Its rows are spaced so that a TEXT comparison
--     and a NUMERIC one disagree: '100' sorts BELOW '20' lexicographically but above it as a
--     number, so a fix that just casts both sides to text is caught, not just an error.
--   * `tax_id` TEXT — the text shape (`customers.list`, `invoice.list`, `cash_register.counts
--     .list`, `services.packages.list` all declare `range` over a TEXT column). One of its
--     values is ALL DIGITS on purpose: a fix that turns any number-looking bound into a number
--     would break this column, which works today.
CREATE TABLE rangefix_event (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  happened_at TEXT NOT NULL,
  logged_on TEXT NOT NULL,
  priority INTEGER NOT NULL,
  tax_id TEXT NOT NULL
);
INSERT INTO rangefix_event (id, hub_id, happened_at, logged_on, priority, tax_id) VALUES
  ('day-before', 'h1', '2026-01-14T23:00:00+00:00', '2026-01-14',   5, '00000001'),
  ('morning',    'h1', '2026-01-15T08:00:00+00:00', '2026-01-15',  10, '12345678'),
  ('evening',    'h1', '2026-01-15T23:30:00+00:00', '2026-01-15',  20, 'B12345678'),
  ('day-after',  'h1', '2026-01-16T00:30:00+00:00', '2026-01-16', 100, '99999999');
