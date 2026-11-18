// Types of `base.bell.counters` for the SDK, from base/schemas/bell.py. Written by hand; base/tests/test_bell.py
// keeps their fields in step with the schema's.

/** `base.BellCounterOut`: a counter above zero, with its words already in the person's language. */
export interface BellCounter {
  /** «<app>.<counter>», or «base.failed_events». */
  key: string;
  app: string;
  count: number;
  route: string;
  label: string;
  icon: string;
  severity: 'danger' | 'warning' | 'info';
  /** Its heading, with its number. */
  title: string;
  /** One sentence with the consequence. */
  body: string | null;
  /** The label of the button that leads to its route. */
  action_label: string;
  /** Its deadline, an ISO date-time. */
  due: string | null;
}

/** `base.BellCountersOut`: the counters above zero, and how often the bell reads them again (none: only on a change). */
export interface BellCounters {
  counters: BellCounter[];
  refresh_every: number | null;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'base.bell.counters': { input: Record<string, never>; output: BellCounters };
  }
}
