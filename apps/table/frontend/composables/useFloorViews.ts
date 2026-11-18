import type { FloorTable } from '@erplora/ui/components';
import { computed, type ComputedRef } from 'vue';

import { floorView } from '../lib/floor-view';
import type { SettingsOut, TableOut } from '../operations';
import { useLocale, useT } from './useT';

export interface FloorViewSource {
  now: Date;
  settings: SettingsOut;
  timeZone: string;
  pick?: ((table: TableOut) => boolean) | null;
}

export function useFloorViews(tables: () => readonly TableOut[], source: () => FloorViewSource): ComputedRef<FloorTable[]> {
  const t = useT();
  const locale = useLocale();
  return computed(() => {
    const options = { ...source(), locale: locale.value, t };
    return tables().map((table) => floorView(table, options));
  });
}
