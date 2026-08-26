-- Unconditional counter UPSERT: always affects exactly 1 row, independent of the booking
-- INSERT's WHERE. This is the statement that neutralized the batch-sum gate.
INSERT INTO gate_settings (hub_id, booking_seq)
VALUES (:hub_id, 1)
ON CONFLICT (hub_id) DO UPDATE SET booking_seq = gate_settings.booking_seq + 1
