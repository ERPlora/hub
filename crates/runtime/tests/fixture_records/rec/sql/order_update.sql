UPDATE rec_order SET customer = :customer, notes = :notes, status = :status WHERE hub_id = :hub_id AND id = :order_id;
