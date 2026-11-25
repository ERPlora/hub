// Types of apps/cash_register/schemas/app_lines.py: what another app (Tips) records in a session as its own.

/** `AppLine`: one line of an app in a session's summary, already named in the reader's language. */
export interface AppLine {
  /** The app that recorded it, by its registry name (`tip`). */
  app: string;
  label: string;
  /** In cents, with its sign: what was paid out of the drawer is negative. */
  amount: number;
}

declare module '../operations' {
  interface SessionSummary {
    /** By app, what came in by payment method and what was paid out; null when a blind count hides it. */
    app_lines: AppLine[] | null;
  }

  interface MovementRow {
    /** Empty for a line written by hand or a sale's. */
    app: string;
    /** The app's name in the reader's language; empty without one. */
    app_name: string;
  }
}
