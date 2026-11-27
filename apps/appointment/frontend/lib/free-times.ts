// The free times of a day split by the spans the professional works, compared on the business's wall clock (the
// first sixteen characters of a server time, see clock.ts).
import type { SlotOut, WindowOut } from '../operations-availability';
import { wallInput } from './clock';

export interface WindowGroup extends WindowOut {
  slots: SlotOut[];
}

const wall = (moment: string): string => moment.slice(0, 16);

/** One group per span, each with the free times that start in it; a time before every span goes to the first. */
export function groupByWindow(windows: readonly WindowOut[], slots: readonly SlotOut[]): WindowGroup[] {
  const groups = windows.map((window) => ({ ...window, slots: [] as SlotOut[] }));
  if (!groups.length) return groups;
  for (const slot of slots) {
    const index = groups.findLastIndex((group) => wall(group.start) <= wall(slot.start));
    groups[Math.max(index, 0)].slots.push(slot);
  }
  return groups;
}

/** The span holding `time` on `day`; else the first with a free time; else the first. */
export function defaultWindow(groups: readonly WindowGroup[], day: string, time: string): number {
  const chosen = time ? wallInput(day, time) : '';
  const holding = groups.findIndex((group) => chosen !== '' && wall(group.start) <= chosen && chosen < wall(group.end));
  if (holding >= 0) return holding;
  return Math.max(
    groups.findIndex((group) => group.slots.length > 0),
    0,
  );
}
