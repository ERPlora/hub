import type { FloorTable } from '@erplora/ui/components';

import type { Translate } from '../composables/useT';
import type { SettingsOut, TableOut } from '../operations';
import { holdName } from './floor';
import { paintedRatio } from './floor-fit';
import { clock, durationTone, minutesSince } from './format';

export interface FloorViewOptions {
  now: Date;
  settings: SettingsOut;
  locale: string;
  timeZone: string;
  t: Translate;
  /** While a transfer or a merge picks its destination: which tables may be picked. */
  pick?: ((table: TableOut) => boolean) | null;
}

type Timing = Pick<FloorTable, 'timed' | 'tone' | 'progress'> & { minutes: number | null };

export function elapsed(minutes: number | null): string {
  if (minutes === null) return '';
  const whole = Math.max(0, Math.floor(minutes));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

function timing(table: TableOut, options: FloorViewOptions): Timing {
  const minutes = table.status === 'occupied' ? minutesSince(table.since, options.now) : null;
  if (minutes === null) return { minutes, timed: false, tone: 'normal', progress: 0 };
  const tone = durationTone('open', minutes, options.settings);
  return {
    minutes,
    timed: true,
    tone: tone === 'ok' ? 'normal' : tone,
    progress: Math.min(100, (minutes / options.settings.timer_critical_minutes) * 100),
  };
}

function accessible(table: TableOut, view: { minutes: number | null; holder: string; holdTime: string }, t: Translate): string {
  const occupied = table.status === 'occupied';
  return [
    t('table.tableLabel', { number: table.number }),
    table.zone_name ?? '',
    table.name,
    t('table.pax', { count: table.capacity }),
    t(`table.status.${table.status}`),
    occupied && table.guests !== null ? t('table.guestsCount', { count: table.guests }) : '',
    occupied && view.minutes !== null ? t('table.minutes', { minutes: view.minutes }) : '',
    occupied && table.waiter_name ? t('table.servedBy', { name: table.waiter_name }) : '',
    table.hold ? t('table.reservedFor', { name: view.holder }) : '',
    view.holdTime,
  ]
    .filter(Boolean)
    .join(' · ');
}

/** A table as the plan and the phone's cards paint it, with every text in the person's language. */
export function floorView(table: TableOut, options: FloorViewOptions): FloorTable {
  const { t } = options;
  const { minutes, ...time } = timing(table, options);
  const statusLabel = t(`table.status.${table.status}`);
  const holdTime = clock(table.hold?.held_from, options.locale, options.timeZone);
  const holder = holdName(table.hold, t('table.erasedCustomer'));
  const pax = table.status === 'occupied' ? t('table.floor.paxOf', { guests: table.guests ?? 0, capacity: table.capacity }) : t('table.pax', { count: table.capacity });
  const short = time.timed ? elapsed(minutes) : table.status === 'reserved' && holdTime ? holdTime : statusLabel;
  return {
    id: table.id,
    number: table.number,
    status: table.status,
    shape: table.shape,
    capacity: table.capacity,
    guests: table.guests,
    ratio: paintedRatio(table),
    ...time,
    short,
    statusLabel,
    caption: short === statusLabel ? pax : `${statusLabel} · ${pax}`,
    pax,
    holder,
    holdTime,
    accessible: accessible(table, { minutes, holder, holdTime }, t),
    pickable: options.pick ? options.pick(table) : undefined,
    testid: `table-floor-tile-${table.id}`,
  };
}
