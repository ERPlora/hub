import type { FloorTable } from '@erplora/ui/components';

import type { Translate } from '../composables/useT';
import type { SettingsOut, TableOut } from '../operations';
import { holdName } from './floor';
import { paintedRatio } from './floor-fit';
import { clock, durationTone, formatMoney, minutesSince, type Money } from './format';

export interface FloorViewOptions {
  now: Date;
  settings: SettingsOut;
  locale: string;
  timeZone: string;
  t: Translate;
  /** While a transfer or a merge picks its destination: which tables may be picked. */
  pick?: ((table: TableOut) => boolean) | null;
  /** The business's currency; until it is known no table shows its bill. */
  money?: Money;
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

function bill(table: TableOut, options: FloorViewOptions): string | undefined {
  if (table.status !== 'occupied' || typeof table.amount !== 'number' || !options.money) return undefined;
  return formatMoney(table.amount, options.locale, options.money);
}

interface Spoken {
  minutes: number | null;
  amount: string | undefined;
  holder: string;
  holdTime: string;
}

function accessible(table: TableOut, view: Spoken, t: Translate): string {
  const occupied = table.status === 'occupied';
  return [
    t('table.tableLabel', { number: table.number }),
    table.zone_name ?? '',
    table.name,
    t('table.pax', { count: table.capacity }),
    t(`table.status.${table.status}`),
    occupied && table.guests !== null ? t('table.guestsCount', { count: table.guests }) : '',
    occupied && view.minutes !== null ? t('table.minutes', { minutes: view.minutes }) : '',
    view.amount ? t('table.floor.bill', { amount: view.amount }) : '',
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
  const amount = bill(table, options);
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
    amount,
    holder,
    holdTime,
    accessible: accessible(table, { minutes, amount, holder, holdTime }, t),
    pickable: options.pick ? options.pick(table) : undefined,
    testid: `table-floor-tile-${table.id}`,
  };
}
