// Types of the free times of a day (`appointment.availability.slots`), from apps/appointment/schemas/availability.py.
// Written by hand, as operations.d.ts: keep them in step with the schemas. Times on the business's clock with its offset.

export interface SlotOut {
  start: string;
  end: string;
  within_notice: boolean;
  staff_ids: string[];
}

// A span of the day the professional works; blocks and appointments do not cut it.
export interface WindowOut {
  start: string;
  end: string;
}

export interface SlotsOut {
  date: string;
  timezone: string;
  duration_minutes: number;
  windows: WindowOut[];
  slots: SlotOut[];
}
