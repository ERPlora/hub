-- hub#1091 fixture: the measured shape of online_booking.bookings.create (online_booking#25).
-- A counter UPSERT that ALWAYS affects 1 next to the guarded INSERT that can miss.
CREATE TABLE gate_settings (
  hub_id TEXT PRIMARY KEY,
  booking_seq INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE gate_booking (
  id TEXT PRIMARY KEY,
  hub_id TEXT NOT NULL,
  ref TEXT NOT NULL
);
