// The days of a scenario (assistant-scenario.ts): `{today}`, `{today±N}` and `{<weekday>}` (the next one, never today)
// written as days of the run, in every text of it, so the owner's «on Friday» and the checks that look for that
// booking name the same day. Pure, so Vitest proves it (assistant-scenario-dates.test.ts).
import type { Scenario } from './assistant-scenario.ts';
import { mapStrings, shifted } from './assistant-setup.ts';

const WEEKDAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

/** The first `weekday` strictly after `today` (YYYY-MM-DD). */
export function nextWeekday(today: string, weekday: string): string {
  const now = new Date(`${today}T00:00:00Z`).getUTCDay();
  const wanted = WEEKDAYS.indexOf(weekday);
  if (wanted < 0) throw new Error(`«${weekday}» is not a weekday`);
  return shifted(today, ((wanted - now + 6) % 7) + 1);
}

const DAY = new RegExp(`\\{(today([+-]\\d+)?|${WEEKDAYS.join('|')})\\}`, 'g');

const dated = (value: unknown, today: string): unknown =>
  mapStrings(value, (text) =>
    text.replace(DAY, (_, name: string, days?: string) => (name.startsWith('today') ? shifted(today, Number(days ?? 0)) : nextWeekday(today, name))),
  );

/** The scenario with `{today}`, `{today±N}` and `{<weekday>}` (the next one) written as days of the run. */
export const datedScenario = (scenario: Scenario, today: string): Scenario => dated(scenario, today) as Scenario;
