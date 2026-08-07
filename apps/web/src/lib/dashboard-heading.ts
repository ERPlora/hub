// What the panel writes in its `<h1>` (hub#366, PLAN step 10).
//
// The header used to greet the session user by name, and for a cloud login that "name" is the
// account address: `Good morning, ioanbeilic@gmail.com`. That is plumbing of the account, not the
// business. The hub is named after the BUSINESS (ADR-0173) and the `<h1>` answers «whose hub is
// this»; who is signed in belongs to the account menu, one place, not two.
//
// The rule lives here, pure, because the fallback is the part that has to be right: on day one the
// hub does NOT know its business name yet — `business_legal_name` (ADR-0061, the hub's single
// business identity) starts empty, nothing in provisioning seeds it, and a blueprint never carries
// it either (the fiscal identity is deliberately outside `PORTABLE_SETTING_KEYS`). So the nameless
// header is the common first screen, not a corner case, and it must read finished.

/** The three time-of-day slots the nameless header greets with. */
export type GreetingSlot = 'morning' | 'afternoon' | 'evening';

/**
 * What the header shows: the business the hub belongs to, or —while the hub still has no name— the
 * hour of the day. There is deliberately no third case that names a person.
 */
export type PanelHeading =
  | { kind: 'business'; name: string }
  | { kind: 'greeting'; slot: GreetingSlot };

/** i18n key per slot. The strings carry NO placeholder: nobody is interpolated into a greeting. */
export const GREETING_KEY: Record<GreetingSlot, string> = {
  morning: 'dashboard.greetingMorning',
  afternoon: 'dashboard.greetingAfternoon',
  evening: 'dashboard.greetingEvening',
};

/** The slot for an hour of the day (0–23, as `Date#getHours()` returns it). */
export function greetingSlot(hour: number): GreetingSlot {
  if (hour < 12) return 'morning';
  if (hour < 20) return 'afternoon';
  return 'evening';
}

/**
 * Is this stored value an email address rather than a business name? Belt and braces: the person is
 * already out by construction (this module is never told who is signed in), but the header is
 * exactly where an address showed up once, so one that reached `business_legal_name` is refused
 * instead of printed. Narrow on purpose — a single token, an `@`, and a dotted domain after it; a
 * real name that happens to contain an `@` («Café @ Home») is still a name.
 */
function isEmailAddress(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

/**
 * Resolves the panel header from the hub's business name and the current hour.
 *
 * @param businessName `hub_settings.business_legal_name` — absent while settings are still loading.
 * @param hour local hour of the day, 0–23.
 */
export function panelHeading(
  businessName: string | null | undefined,
  hour: number,
): PanelHeading {
  const name = (businessName ?? '').trim();
  if (name && !isEmailAddress(name)) return { kind: 'business', name };
  return { kind: 'greeting', slot: greetingSlot(hour) };
}
