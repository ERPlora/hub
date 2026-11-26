// The period of a tips screen: «Today» to begin with, «7 days» or «30 days», counted back from the hub's business day,
// which is read on opening and again on every pick (the day may have turned while the screen was open).
import { computed, type ComputedRef, onMounted, type Ref, shallowRef } from 'vue';

import { type DayBounds, periodBounds } from '../../../sale/frontend/components/sales/period';
import { useBusinessDay } from '../../../sale/frontend/components/sales/useBusinessDay';

export const PERIODS = ['today', 'week', 'month'] as const;
export type Period = (typeof PERIODS)[number];

export interface TipPeriod {
  period: Readonly<Ref<Period>>;
  /** The business days it covers, both included. */
  bounds: ComputedRef<DayBounds>;
  /** Moves to `value` when it is one of `PERIODS`. */
  pick: (value: unknown) => void;
}

export function usePeriod(): TipPeriod {
  const day = useBusinessDay();
  onMounted(() => void day.read());
  const period = shallowRef<Period>('today');
  const bounds = computed(() => periodBounds(period.value, day.today.value));
  function pick(value: unknown): void {
    if (!PERIODS.includes(value as Period)) return;
    period.value = value as Period;
    void day.read();
  }
  return { period, bounds, pick };
}
