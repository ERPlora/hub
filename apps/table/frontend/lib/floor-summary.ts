import type { TableOut } from '../operations';

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
