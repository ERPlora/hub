// The weekdays as the slots count them: 0 = Monday … 6 = Sunday (the old module's and Python's order).
export const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const;

/** The catalogue key of weekday `index`; empty for an index that is no weekday. */
export function weekdayKey(index: number): string {
  const name = WEEKDAYS[index];
  return name ? `reservation.weekday.${name}` : '';
}
