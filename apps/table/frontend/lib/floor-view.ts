import type { Translate } from '../composables/useT';
import type { SettingsOut, TableOut } from '../operations';
import { clock, durationTone, minutesSince } from './format';
import { holdName } from './floor';

export interface FloorViewOptions {
  now: Date;
  settings: SettingsOut;
  locale: string;
  timeZone: string;
  t: Translate;
}

export interface FloorView {
  minutes: number | null;
  tone: 'normal' | 'warning' | 'critical';
  progress: number;
  short: string;
  pax: string;
  holder: string;
  holdTime: string;
  labels: string[];
  accessible: string;
}

export function elapsed(minutes: number | null): string {
  if (minutes === null) return '';
  const whole = Math.max(0, Math.floor(minutes));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

function accessible(table: TableOut, model: Omit<FloorView, 'accessible'>, options: FloorViewOptions): string {
  const { t } = options;
  return [
    t('table.tableLabel', { number: table.number }),
    table.zone_name ?? '',
    table.name,
    t('table.pax', { count: table.capacity }),
    t(`table.status.${table.status}`),
    table.status === 'occupied' && table.guests !== null ? t('table.guestsCount', { count: table.guests }) : '',
    model.minutes !== null && table.status === 'occupied' ? t('table.minutes', { minutes: model.minutes }) : '',
    table.status === 'occupied' && table.waiter_name ? t('table.servedBy', { name: table.waiter_name }) : '',
    table.hold ? t('table.reservedFor', { name: holdName(table.hold, t('table.erasedCustomer')) }) : '',
    model.holdTime,
  ]
    .filter(Boolean)
    .join(' · ');
}

export function floorView(table: TableOut, options: FloorViewOptions): FloorView {
  const { t } = options;
  const minutes = table.status === 'occupied' ? minutesSince(table.since, options.now) : null;
  const rawTone = minutes === null ? 'ok' : durationTone('open', minutes, options.settings);
  const status = t(`table.status.${table.status}`);
  const holdTime = clock(table.hold?.held_from, options.locale, options.timeZone);
  const holder = holdName(table.hold, t('table.erasedCustomer'));
  const pax = table.status === 'occupied' ? t('table.floor.paxOf', { guests: table.guests ?? 0, capacity: table.capacity }) : t('table.pax', { count: table.capacity });
  const short = minutes !== null ? elapsed(minutes) : table.status === 'reserved' && holdTime ? holdTime : status;
  const model = {
    minutes,
    tone: rawTone === 'ok' ? ('normal' as const) : rawTone,
    progress: minutes === null ? 0 : Math.min(100, (minutes / options.settings.timer_critical_minutes) * 100),
    short,
    pax,
    holder,
    holdTime,
    labels: [short === status ? pax : `${status} · ${pax}`, ...(holder ? [`${holder}${holdTime ? ` · ${holdTime}` : ''}`] : [])],
  };
  return { ...model, accessible: accessible(table, model, options) };
}
