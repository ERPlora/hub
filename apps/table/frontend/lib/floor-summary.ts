import type { FloorStat, FloorZoneTab } from '@erplora/ui/components';

import type { Translate } from '../composables/useT';
import type { TableOut, ZoneOut } from '../operations';

export interface ZoneCounts {
  occupied: number;
  total: number;
}

export interface RoomSummary {
  available: number;
  occupied: number;
  reserved: number;
  guests: number;
}

export function zoneCounts(tables: readonly TableOut[]): ZoneCounts {
  const service = tables.filter((table) => table.in_service);
  return { occupied: service.filter((table) => table.status === 'occupied').length, total: service.length };
}

export function roomSummary(tables: readonly TableOut[]): RoomSummary {
  return {
    available: tables.filter((table) => table.status === 'available').length,
    occupied: tables.filter((table) => table.status === 'occupied').length,
    reserved: tables.filter((table) => table.status === 'reserved').length,
    guests: tables.reduce((sum, table) => sum + (table.status === 'occupied' ? (table.guests ?? 0) : 0), 0),
  };
}

export interface ZoneSummary {
  title: string;
  subtitle: string;
  color: string | null;
  stats: FloorStat[];
}

function occupiedOf(counts: ZoneCounts, t: Translate): string {
  return t('table.floor.summary.occupiedOf', { occupied: counts.occupied, count: counts.total });
}

/** The zone tabs of the plan, each counting the tables of its zone among `tables` (every zone's, as painted now). */
export function zoneTabs(zones: readonly ZoneOut[], tables: readonly TableOut[], t: Translate): FloorZoneTab[] {
  return zones.map((zone) => {
    const counts = zoneCounts(tables.filter((table) => table.zone_id === zone.id));
    return { id: zone.id, name: zone.name, color: zone.color, ...counts, said: occupiedOf(counts, t), testid: `table-floor-zone-tab-${zone.id}` };
  });
}

/** The summary above the plan of `zone`, from its tables in service as painted now. */
export function zoneSummary(zone: ZoneOut | null, tables: readonly TableOut[], t: Translate): ZoneSummary {
  const sums = roomSummary(tables);
  const stats = (['available', 'occupied', 'reserved', 'guests'] as const).map((key) => ({ key, value: sums[key], label: t(`table.floor.summary.${key}`) }));
  return { title: zone?.name ?? '', subtitle: occupiedOf(zoneCounts(tables), t), color: zone?.color ?? null, stats };
}
